import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name in ("backend", "scripts", "src") else BASE_DIR
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import config
except ImportError:
    config = None


def resolve_config_path(attr_names, default_rel_path):
    """configモジュールまたはプロジェクトルート基準でパスを解決する"""
    for name in (attr_names if config else ()):
        if getattr(config, name, None):
            return Path(getattr(config, name))
    return PROJECT_ROOT / default_rel_path


DRAFT_FILE = resolve_config_path(["DRAFT_FILE", "WEEKLY_DRAFT_FILE"], "data/drafts/weekly_draft.json")
BACKUP_DRAFT_FILE = resolve_config_path(["BACKUP_DRAFT_FILE", "WEEKLY_DRAFT_BACKUP_FILE"], "data/drafts/weekly_draft.backup.json")
PUBLIC_LATEST = resolve_config_path(["PUBLIC_LATEST", "LATEST_RANKING_FILE"], "public/data/latest_ranking.json")
ARCHIVE_DIR = resolve_config_path(["ARCHIVE_DIR", "ARCHIVES_DIR"], "public/data/archives")
ARCHIVE_INDEX = resolve_config_path(["ARCHIVE_INDEX"], "public/data/archives/archive_index.json")
ARTICLES_MASTER_FILE = resolve_config_path(["ARTICLES_MASTER_FILE"], "data/articles/articles_master.json")
PUBLIC_ARTICLES_FILE = resolve_config_path(["PUBLIC_ARTICLES_FILE"], "public/data/articles.json")

SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google/YouTube API Key"),
    (re.compile(r"gh[pousr]_[0-9A-Za-z]{36,255}"), "GitHub Personal Access Token"),
    (re.compile(r"github_pat_[0-9A-Za-z_]{50,255}"), "GitHub Fine-grained Token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "Private Key"),
]
LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\Users\\[^\\\"\'\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z]:/Users/[^/\"\'\s]+", re.IGNORECASE),
    re.compile(r"/Users/[^/\"\'\s]+"),
]

def inspect_and_redact_text(text, label="data"):
    """秘密鍵・APIキーの混入をブロックし、PCローカルパスをマスクする"""
    if not text:
        return text
    for regex, secret_name in SECRET_PATTERNS:
        if regex.search(text):
            raise RuntimeError(f"[SECURITY BLOCK] {label} 内に機密情報 ({secret_name}) の混入を検知したため、公開処理を緊急停止しました。")
    redacted = text
    for path_regex in LOCAL_PATH_PATTERNS:
        redacted = path_regex.sub("[REDACTED_PATH]", redacted)
    return redacted

def load_json(filepath, default=None):
    path_obj = Path(filepath)
    if not path_obj.exists():
        return default
    try:
        return json.loads(path_obj.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] JSON読み込み失敗 ({path_obj}): {e}")
        return default

def save_json(filepath, data):
    path_obj = Path(filepath)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    safe_json = inspect_and_redact_text(json.dumps(data, ensure_ascii=False, indent=2), label=path_obj.name)
    path_obj.write_text(safe_json + "\n", encoding="utf-8")

def _iter_archive_jsons():
    """ARCHIVE_DIR 内のアーカイブJSONファイルと読込済み辞書を列挙する"""
    if not ARCHIVE_DIR.exists():
        return
    for p in sorted(ARCHIVE_DIR.glob("*.json")):
        if p.name not in ("archive_index.json", "index.json"):
            data = load_json(p)
            if isinstance(data, dict):
                yield p, data


def normalize_period_str(period_str, now_dt=None):
    """集計期間文字列を 'YYYY/MM/DD - YYYY/MM/DD' 形式へ正規化する"""
    if now_dt is None:
        now_dt = datetime.now(JST)
    if not period_str or not isinstance(period_str, str):
        today = now_dt.date()
        this_monday = today - timedelta(days=today.weekday())
        return f"{(this_monday - timedelta(days=7)).strftime('%Y/%m/%d')} - {(this_monday - timedelta(days=1)).strftime('%Y/%m/%d')}"

    m = re.match(r"^\s*(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\s*[\-~〜]\s*(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\s*$", period_str)
    if not m:
        return period_str
    start_d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    end_d = date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
    if (end_d - start_d).days == 7:
        end_d = end_d - timedelta(days=1)
    return f"{start_d.strftime('%Y/%m/%d')} - {end_d.strftime('%Y/%m/%d')}"


def infer_archive_id_and_period(chart_data: dict, fallback_id: str = ""):
    """チャート辞書から一意な archiveId (YYYY-MM-DD) と正規化 period を推論する"""
    if not isinstance(chart_data, dict):
        return "", ""
    raw_period = str(chart_data.get("period") or "").strip()
    norm_period = normalize_period_str(raw_period) if raw_period else ""
    inferred_wed = ""

    m_p = re.match(r"^\s*(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\s*[\-~〜]", raw_period)
    if m_p:
        inferred_wed = (date(int(m_p.group(1)), int(m_p.group(2)), int(m_p.group(3))) + timedelta(days=9)).strftime("%Y-%m-%d")

    aid = ""
    for field in (chart_data.get("archiveId"), chart_data.get("publishDate"), fallback_id):
        m_d = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(field or "").strip())
        if m_d:
            aid = f"{m_d.group(1)}-{m_d.group(2)}-{m_d.group(3)}"
            break
    return aid or inferred_wed, norm_period


def get_release_datetime_jst(chart_data: dict) -> datetime:
    """チャートデータの公開解禁日時(JST)を返す"""
    if not isinstance(chart_data, dict):
        return datetime.min.replace(tzinfo=JST)
    pub_at_str = chart_data.get("publishAt")
    if isinstance(pub_at_str, str) and pub_at_str.strip():
        try:
            cleaned = pub_at_str.strip()
            dt = datetime.fromisoformat(cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned)
            return (dt.replace(tzinfo=JST) if dt.tzinfo is None else dt).astimezone(JST)
        except Exception:
            pass
    pub_date_str = str(chart_data.get("publishDate") or chart_data.get("archiveId") or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{1,2}):(\d{2}))?", pub_date_str)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 13), int(m.group(5) or 0), 0, tzinfo=JST)
    return datetime.min.replace(tzinfo=JST)

def is_chart_released(chart_data: dict, now_dt: datetime = None) -> bool:
    """公開時刻を過ぎているかを判定する"""
    return (now_dt or datetime.now(JST)) >= get_release_datetime_jst(chart_data)

def _chart_quality_score(chart_data: dict, fallback_aid: str = "") -> tuple:
    """解説文中のpt表記とtotal_ptの一致数・水曜前集計・解説件数で品質スコアを算出する"""
    if not isinstance(chart_data, dict):
        return (0, 0, 0)
    songs = chart_data.get("ranking") or chart_data.get("songs") or []
    aid, _ = infer_archive_id_and_period(chart_data, fallback_id=fallback_aid)
    upd = str(chart_data.get("updated_at") or "").strip()[:10]
    pt_match, com_cnt = 0, 0
    for s in songs:
        com = str(s.get("commentary") or "").strip() if isinstance(s, dict) else ""
        if com:
            com_cnt += 1
            if f"{int(s.get('total_pt') or 0):,}" in com:
                pt_match += 1
    pre_wed = 1 if (aid and re.match(r"^\d{4}-\d{2}-\d{2}$", upd) and upd < aid) else 0
    return (pt_match, pre_wed, com_cnt)

def _normalize_chart_metadata(data: dict, fallback_id: str = ""):
    """アーカイブJSONのメタデータを正規化し、(data, changed)を返す"""
    aid, norm_period = infer_archive_id_and_period(data, fallback_id=fallback_id)
    if not aid:
        return data, False
    expected = {"archiveId": aid, "publishDate": aid, "publishAt": f"{aid}T13:00:00+09:00"}
    if norm_period:
        expected["period"] = norm_period
    changed = any(data.get(k) != v for k, v in expected.items())
    if changed:
        data.update(expected)
    songs = data.get("songs") or data.get("ranking") or []
    if songs and ("ranking" not in data or "songs" not in data):
        data["songs"] = songs
        data["ranking"] = songs
        changed = True
    return data, changed

def _run_git_stdout(args: list) -> str:
    try:
        res = subprocess.run(["git"] + args, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        return res.stdout if res.returncode == 0 else ""
    except Exception:
        return ""

def _collect_git_history_commits() -> list:
    """執筆スタジオ確定コミット全件＋直近データ変更コミット25件を新しい順で収集する"""
    queries = [
        ["log", "--grep=執筆スタジオ", "--format=%ct %H"],
        ["log", "-n25", "--format=%ct %H", "--", "data/drafts/weekly_draft.json", "public/data/latest_ranking.json"],
    ]
    by_hash = {}
    for cmd in queries:
        for line in _run_git_stdout(cmd).splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[0].isdigit():
                by_hash[parts[1]] = max(by_hash.get(parts[1], 0), int(parts[0]))
    return [h for h, _ in sorted(by_hash.items(), key=lambda kv: kv[1], reverse=True)]

def _git_show_json(commit_hash: str, rel_path: str):
    out = _run_git_stdout(["show", f"{commit_hash}:{rel_path}"])
    try:
        return json.loads(out) if out.strip() else None
    except Exception:
        return None


def archive_existing_latest(incoming_archive_id: str = None):
    """latest_ranking.json 上書き前に既存公開データをアーカイブフォルダへ自動退避する"""
    current = load_json(PUBLIC_LATEST)
    if not isinstance(current, dict) or not (current.get("songs") or current.get("ranking")):
        return
    aid, _ = infer_archive_id_and_period(current)
    if not aid or (incoming_archive_id and aid == incoming_archive_id):
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_file = ARCHIVE_DIR / f"{aid}.json"
    if not out_file.exists():
        norm_data, _ = _normalize_chart_metadata(current, fallback_id=aid)
        save_json(out_file, norm_data)
        print(f"[ARCHIVE BACKUP] 上書き前の最新チャート ({aid}) をアーカイブへ退避しました: {out_file.name}")


def _merge_missing_commentaries(target_chart: dict, donor_charts: list):
    """確定チャートで未記入の解説・総括があれば同一週の他候補から補完する"""
    for meta_key in ("weeklySummary", "overall_commentary", "trend_analysis"):
        if not str(target_chart.get(meta_key) or "").strip():
            for dc in donor_charts:
                if str(dc.get(meta_key) or "").strip():
                    target_chart[meta_key] = dc[meta_key]
                    break
    comment_map = {}
    for dc in donor_charts:
        for s in (dc.get("songs") or dc.get("ranking") or []):
            if isinstance(s, dict) and str(s.get("commentary") or "").strip():
                sid = s.get("song_id") or s.get("id") or s.get("youtube_id") or s.get("niconico_id")
                if sid and sid not in comment_map:
                    comment_map[sid] = s["commentary"]
    for s in (target_chart.get("songs") or target_chart.get("ranking") or []):
        if isinstance(s, dict) and not str(s.get("commentary") or "").strip():
            sid = s.get("song_id") or s.get("id") or s.get("youtube_id") or s.get("niconico_id")
            if sid in comment_map:
                s["commentary"] = comment_map[sid]


def rescue_and_repair_past_archives(current_archive_id: str = None):
    """Git履歴から過去アーカイブの欠損救出・月曜確定値修復・メタデータ正規化を行う"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    disk_charts = {}
    for p, d in _iter_archive_jsons():
        if d.get("songs") or d.get("ranking"):
            aid, _ = infer_archive_id_and_period(d, fallback_id=p.stem)
            if aid:
                disk_charts[aid] = (p, d, _chart_quality_score(d, aid))

    best_git, git_donors = {}, {}
    for chash in _collect_git_history_commits():
        for rel_p in ("data/drafts/weekly_draft.json", "public/data/latest_ranking.json"):
            d = _git_show_json(chash, rel_p)
            if not isinstance(d, dict) or len(d.get("songs") or d.get("ranking") or []) < 5:
                continue
            aid, _ = infer_archive_id_and_period(d)
            if not aid or (current_archive_id and aid == current_archive_id):
                continue
            git_donors.setdefault(aid, []).append(d)
            score = _chart_quality_score(d, aid)
            if aid not in best_git or score > best_git[aid][0]:
                best_git[aid] = (score, d)

    for aid, (git_score, git_chart) in best_git.items():
        disk_entry = disk_charts.get(aid)
        if disk_entry is not None and not (git_score > disk_entry[2] and (git_score[0] >= 5 or git_score[1] > disk_entry[2][1])):
            continue
        restored = json.loads(json.dumps(git_chart, ensure_ascii=False))
        _merge_missing_commentaries(restored, ([disk_entry[1]] if disk_entry else []) + git_donors.get(aid, []))
        if disk_entry and disk_entry[1].get("published_at") and not restored.get("published_at"):
            restored["published_at"] = disk_entry[1]["published_at"]
        _normalize_chart_metadata(restored, fallback_id=aid)
        out_path = ARCHIVE_DIR / f"{aid}.json"
        save_json(out_path, restored)
        disk_charts[aid] = (out_path, restored, _chart_quality_score(restored, aid))
        print(f"[ARCHIVE REPAIR] Git履歴から過去ランキング ({aid}) を{'復元' if disk_entry is None else '月曜確定版へ修復'}しました: {out_path.name}")

    for aid, (p, d, _) in disk_charts.items():
        if not current_archive_id or aid != current_archive_id:
            norm_d, changed = _normalize_chart_metadata(d, fallback_id=aid)
            if changed:
                save_json(p, norm_d)

def rebuild_archive_index(now_dt: datetime = None) -> list:
    """公開済みアーカイブフォルダの全JSONを走査し archive_index.json を完全再構築する"""
    now_dt = now_dt or datetime.now(JST)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for p, data in _iter_archive_jsons():
        if not (data.get("songs") or data.get("ranking")) or not is_chart_released(data, now_dt):
            continue
        aid, norm_period = infer_archive_id_and_period(data, fallback_id=p.stem)
        if not aid:
            continue
        period_str = norm_period or normalize_period_str(data.get("period"), now_dt)
        entries.append({
            "id": aid, "archiveId": aid, "file": p.name, "period": period_str,
            "publishDate": aid, "publishAt": data.get("publishAt") or f"{aid}T13:00:00+09:00",
            "label": f"{aid} 公開 ({period_str})",
        })

    entries.sort(key=lambda x: x["archiveId"], reverse=True)
    existing = load_json(ARCHIVE_INDEX, default=[])
    payload = {"archives": entries} if (isinstance(existing, dict) and "archives" in existing) else entries
    for t in [ARCHIVE_INDEX, PROJECT_ROOT / "public/data/archive_index.json"] + ([PROJECT_ROOT / "data/archive_index.json"] if (PROJECT_ROOT / "data/archive_index.json").exists() else []):
        save_json(t, payload)
    print(f"[ARCHIVE INDEX] アーカイブ目次を再構築しました ({len(entries)} 件)")
    return entries

def update_archive_index(archive_id, period_str, publish_date, publish_at):
    """後方互換ラッパー：全アーカイブを走査して目次を再構築する"""
    return rebuild_archive_index()

def rollback_unreleased_public_files(now_dt: datetime = None):
    """解禁前のランキングが公開領域にあれば直前の公開済みチャートへロールバックする"""
    now_dt = now_dt or datetime.now(JST)
    released = []
    for p, data in _iter_archive_jsons():
        if not is_chart_released(data, now_dt):
            print(f"[ROLLBACK] 解禁時刻前のアーカイブを退避削除しました: {p.name}")
            p.unlink(missing_ok=True)
        else:
            released.append((str(data.get("archiveId") or p.stem), data))

    current_public = load_json(PUBLIC_LATEST)
    if isinstance(current_public, dict) and not is_chart_released(current_public, now_dt) and released:
        released.sort(key=lambda x: x[0], reverse=True)
        for out_p in (PUBLIC_LATEST, PROJECT_ROOT / "data/latest_ranking.json"):
            save_json(out_p, released[0][1])
        print(f"[ROLLBACK] latest_ranking.json を直前公開済み ({released[0][0]}) に復元しました。")
    rebuild_archive_index(now_dt)
