import os
import re
import sys
import json
import glob
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

try:
    import config
except ImportError:
    config = None

JST = timezone(timedelta(hours=9))

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name in ("backend", "scripts", "src") else BASE_DIR
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from vocaloid_filter import build_canonical_originals_map, clean_song_title, is_eligible_ranking_song


def resolve_config_path(attr_names, default_rel_path):
    if config:
        for name in attr_names:
            if hasattr(config, name):
                val = getattr(config, name)
                if val:
                    return Path(val)
    return PROJECT_ROOT / default_rel_path


MASTER_FILE = resolve_config_path(["MASTER_FILE", "SONGS_MASTER_FILE"], "data/master/songs_master.json")
SNAPSHOTS_DIR = resolve_config_path(["SNAPSHOTS_DIR", "SNAPSHOT_DIR"], "data/snapshots")
LATEST_SNAPSHOT = resolve_config_path(["LATEST_SNAPSHOT"], "data/snapshots/latest_monday.json")
PREV_SNAPSHOT = resolve_config_path(["PREV_SNAPSHOT"], "data/snapshots/prev_monday.json")
DRAFT_FILE = resolve_config_path(["DRAFT_FILE", "WEEKLY_DRAFT_FILE"], "data/drafts/weekly_draft.json")
BACKUP_DRAFT_FILE = resolve_config_path(["BACKUP_DRAFT_FILE", "WEEKLY_DRAFT_BACKUP_FILE"], "data/drafts/weekly_draft.backup.json")
PUBLIC_LATEST = resolve_config_path(["PUBLIC_LATEST", "LATEST_RANKING_FILE"], "public/data/latest_ranking.json")
ARCHIVE_DIR = resolve_config_path(["ARCHIVE_DIR", "ARCHIVES_DIR"], "public/data/archives")
ARCHIVE_INDEX = resolve_config_path(["ARCHIVE_INDEX"], "public/data/archives/archive_index.json")
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"

DEFAULT_WEIGHTS = {
    "yt_views": 1,
    "yt_likes": 50,
    "yt_comments": 100,
    "nc_views": 5,
    "nc_mylist": 100,
    "nc_mylists": 100,
    "nc_comments": 10,
}
WEIGHTS = getattr(config, "WEIGHTS", DEFAULT_WEIGHTS) if config else DEFAULT_WEIGHTS
TOP_N = getattr(config, "TOP_N", 20) if config else 20

MAX_NEW_SONG_AGE_DAYS = 10.0


def load_json(filepath, default=None):
    path_obj = Path(filepath)
    if not path_obj.exists():
        return default
    try:
        with open(path_obj, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] JSON読み込み失敗 ({path_obj}): {e}")
        return default


def save_json(filepath, data):
    path_obj = Path(filepath)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with open(path_obj, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_songs_list(data):
    if not data:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("songs", "ranking", "metrics", "items", "data"):
            if key in data and isinstance(data[key], list):
                return [item for item in data[key] if isinstance(item, dict)]
        vals = list(data.values())
        if vals and all(isinstance(v, dict) for v in vals):
            return vals
    return []


def get_song_keys(song_obj):
    if not isinstance(song_obj, dict):
        return set()
    keys = set()
    song_id = song_obj.get("song_id") or song_obj.get("id")
    yt_id = song_obj.get("youtube_id") or song_obj.get("yt_id")
    nc_id = song_obj.get("niconico_id") or song_obj.get("nc_id") or song_obj.get("sm_id")
    if song_id:
        keys.add(f"id:{song_id}")
    if yt_id:
        keys.add(f"yt:{yt_id}")
    if nc_id:
        keys.add(f"nc:{nc_id}")
    return keys


def _git_log_commits(rel_paths: list, max_count: int = 60) -> list:
    try:
        res = subprocess.run(
            ["git", "log", f"-n{max_count}", "--format=%H", "--"] + rel_paths,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []


def _git_show_json(commit_hash: str, rel_path: str):
    try:
        res = subprocess.run(
            ["git", "show", f"{commit_hash}:{rel_path}"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return None


def infer_archive_id_and_period(chart_data: dict) -> tuple:
    """チャート辞書から一意な archiveId (YYYY-MM-DD: 水曜公開日) と正規化 period を推論する"""
    if not isinstance(chart_data, dict):
        return "", ""

    raw_period = str(chart_data.get("period") or "").strip()
    norm_period = raw_period
    inferred_wed = ""

    m = re.match(
        r"^\s*(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\s*[\-~〜]\s*(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\s*$",
        raw_period,
    )
    if m:
        start_d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        end_d = date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        if (end_d - start_d).days == 7:
            end_d = end_d - timedelta(days=1)
        norm_period = f"{start_d.strftime('%Y/%m/%d')} - {end_d.strftime('%Y/%m/%d')}"
        # 集計開始月曜の9日後＝翌週水曜日（公開日）
        wed_d = start_d + timedelta(days=9)
        inferred_wed = wed_d.strftime("%Y-%m-%d")

    aid = str(chart_data.get("archiveId") or chart_data.get("publishDate") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", aid):
        if inferred_wed:
            aid = inferred_wed
        else:
            for field in ("published_at", "updated_at"):
                val = str(chart_data.get(field) or "").strip()
                m_dt = re.match(r"^(\d{4})[\/\-](\d{2})[\/\-](\d{2})", val)
                if m_dt:
                    aid = f"{m_dt.group(1)}-{m_dt.group(2)}-{m_dt.group(3)}"
                    break

    return aid, norm_period


def rescue_past_archives_from_git(current_archive_id: str):
    """
    Git履歴にある過去の latest_ranking.json / weekly_draft.json から、
    上書き等で消えてしまった過去週のランキング（例: 2026-10-14公開分など）を自動救出し、
    public/data/archives/ および data/archives/ に復元する。
    """
    rel_Targets = [
        "public/data/latest_ranking.json",
        "data/latest_ranking.json",
        "data/drafts/weekly_draft.json",
        "data/weekly_draft.json",
    ]
    commits = _git_log_commits(rel_Targets, max_count=80)
    rescued_by_id = {}

    # 古いコミットから新しいコミットの順に走査し、過去週の最終状態（解説入り）を取得
    for chash in reversed(commits):
        for rel_p in rel_Targets:
            data = _git_show_json(chash, rel_p)
            if not isinstance(data, dict):
                continue
            songs = extract_songs_list(data)
            if not songs:
                continue
            aid, norm_prd = infer_archive_id_and_period(data)
            if not aid or aid >= current_archive_id:
                continue

            data["archiveId"] = aid
            data["publishDate"] = aid
            data["publishAt"] = data.get("publishAt") or f"{aid}T13:00:00+09:00"
            if norm_prd:
                data["period"] = norm_prd
            data["songs"] = songs
            data["ranking"] = songs

            # 既に救出候補がある場合、解説文がより充実している方を優先して保持
            if aid in rescued_by_id:
                old_c = sum(1 for s in extract_songs_list(rescued_by_id[aid]) if s.get("commentary"))
                new_c = sum(1 for s in songs if s.get("commentary"))
                if new_c >= old_c:
                    rescued_by_id[aid] = data
            else:
                rescued_by_id[aid] = data

    for aid, chart_obj in rescued_by_id.items():
        for out_dir in (ARCHIVE_DIR, PROJECT_ROOT / "data/archives"):
            out_file = out_dir / f"{aid}.json"
            if not out_file.exists():
                save_json(out_file, chart_obj)
                print(f"[ARCHIVE RESCUE] Git履歴から過去ランキング ({aid}) を復元しました: {out_file}")


def parse_iso_datetime(dt_str):
    if not dt_str or not isinstance(dt_str, str):
        return None
    cleaned = dt_str.strip()
    if not cleaned:
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(cleaned[:19], fmt).replace(tzinfo=JST)
            except Exception:
                continue
    return None


def resolve_earliest_published_dt(*dict_objs):
    candidates = []
    for d in dict_objs:
        if not isinstance(d, dict):
            continue
        for field in ("published_at", "yt_published_at", "nc_published_at", "first_retrieve", "startTime"):
            val = d.get(field)
            if val:
                dt = parse_iso_datetime(str(val))
                if dt:
                    candidates.append(dt)
    if not candidates:
        return None
    return min(candidates)


def resolve_platform_published_dt(platform_prefix, *dict_objs):
    specific_field = f"{platform_prefix}_published_at"
    for d in dict_objs:
        if isinstance(d, dict) and d.get(specific_field):
            dt = parse_iso_datetime(str(d.get(specific_field)))
            if dt:
                return dt
    return resolve_earliest_published_dt(*dict_objs)


def compute_new_release_factor(pub_dt, ref_dt):
    if pub_dt is None or ref_dt is None:
        return 0.0

    age_days = (ref_dt - pub_dt).total_seconds() / 86400.0
    if age_days < -1.0:
        return 1.0
    if age_days > MAX_NEW_SONG_AGE_DAYS:
        return 0.0
    if age_days <= 7.0:
        return 1.0
    return round(7.0 / age_days, 4)


def compute_chart_dates(now_dt=None):
    if now_dt is None:
        now_dt = datetime.now(JST)
    today = now_dt.date()
    this_monday = today - timedelta(days=today.weekday())
    start_date = this_monday - timedelta(days=7)
    end_date = this_monday - timedelta(days=1)
    period_str = f"{start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')}"

    wed_date = this_monday + timedelta(days=2)
    publish_date = wed_date.strftime("%Y-%m-%d")
    archive_id = wed_date.strftime("%Y-%m-%d")
    publish_at = f"{publish_date}T13:00:00+09:00"
    reference_dt = datetime(this_monday.year, this_monday.month, this_monday.day, 0, 0, 0, tzinfo=JST)
    return period_str, publish_date, archive_id, publish_at, reference_dt


def extract_metrics_dict(snapshot_data):
    items = extract_songs_list(snapshot_data)
    result = {}
    for v in items:
        for sk in get_song_keys(v):
            result[sk] = v
    return result


def get_two_latest_snapshots():
    latest_data = load_json(LATEST_SNAPSHOT)
    prev_data = load_json(PREV_SNAPSHOT)

    if latest_data is not None:
        return latest_data, prev_data if prev_data is not None else []

    if not SNAPSHOTS_DIR.exists():
        return [], []

    files = sorted(
        [Path(p) for p in glob.glob(str(SNAPSHOTS_DIR / "*.json"))],
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        return [], []
    latest_f = files[-1]
    prev_f = files[-2] if len(files) >= 2 else None
    return load_json(latest_f, []), load_json(prev_f, []) if prev_f else []


def collect_past_charts(exclude_archive_id=None, exclude_period=None):
    candidate_dirs = [
        ARCHIVE_DIR,
        PROJECT_ROOT / "public/data/archives",
        PROJECT_ROOT / "data/archives",
    ]
    chart_files = []
    for d in candidate_dirs:
        if d.exists():
            chart_files.extend(glob.glob(str(d / "*.json")))

    if PUBLIC_LATEST.exists():
        chart_files.append(str(PUBLIC_LATEST))

    charts_by_key = {}
    for fpath in chart_files:
        fname = os.path.basename(fpath)
        if fname in ("archive_index.json", "index.json"):
            continue
        data = load_json(fpath)
        if not isinstance(data, dict):
            continue
        songs = extract_songs_list(data)
        if not songs:
            continue

        aid, norm_prd = infer_archive_id_and_period(data)
        prd = norm_prd or data.get("period")
        key = aid or prd or os.path.splitext(fname)[0]

        if exclude_archive_id and aid == exclude_archive_id:
            continue
        if exclude_period and prd == exclude_period:
            continue

        charts_by_key[key] = data

    sorted_keys = sorted(charts_by_key.keys())
    return [charts_by_key[k] for k in sorted_keys]


def build_historical_stats(past_charts):
    appearance_counts = {}
    prev_chart_map = {}

    for chart in past_charts:
        ranking_list = extract_songs_list(chart)
        for item in ranking_list[:TOP_N]:
            for k in get_song_keys(item):
                appearance_counts[k] = appearance_counts.get(k, 0) + 1

    if past_charts:
        last_chart = past_charts[-1]
        for idx, item in enumerate(extract_songs_list(last_chart)[:TOP_N], start=1):
            info = {
                "prev_rank": item.get("rank", idx),
                "prev_total_pt": item.get("total_pt", item.get("total_points", 0)),
                "prev_chart_in_count": item.get("chart_in_count", 0),
            }
            for k in get_song_keys(item):
                prev_chart_map[k] = info

    return appearance_counts, prev_chart_map


def find_monday_locked_draft_and_preserve_edits(archive_id: str, period_str: str):
    """
    【月曜ドラフト固定ロック＆執筆データ完全保護システム】
    1. Git履歴とローカルファイルの両方から、今週（archive_id）の解説文(commentary)・総括(weeklySummary)・
       表記修正(title/producer/vocal)を漏れなく収集する。
    2. Git履歴に今週（archive_id）の初回ドラフト（月曜集計時の20曲・ポイント・順位）が存在する場合は、
       週途中の再実行で順位やポイントが変わらないよう、初回ドラフトの順位・ポイントを基準としてロックする。
    """
    saved_song_comments = {}
    saved_song_edits = {}
    saved_meta = {}
    earliest_week_draft = None

    rel_draft_paths = [
        "data/drafts/weekly_draft.json",
        "data/weekly_draft.json",
        "public/data/latest_ranking.json",
    ]
    commits = _git_log_commits(rel_draft_paths, max_count=50)

    def _harvest_from_dict(data_dict: dict):
        if not isinstance(data_dict, dict):
            return
        for meta_key in ("weeklySummary", "overall_commentary", "trend_analysis", "editor_note"):
            val = data_dict.get(meta_key)
            if val and str(val).strip():
                saved_meta[meta_key] = str(val).strip()

        for item in extract_songs_list(data_dict):
            keys = get_song_keys(item)
            comment = item.get("commentary") or item.get("comment")
            if comment and str(comment).strip():
                for k in keys:
                    saved_song_comments[k] = str(comment).strip()
            edits = {}
            for fld in ("title", "producer", "vocal"):
                if item.get(fld) and str(item.get(fld)).strip():
                    edits[fld] = str(item.get(fld)).strip()
            if edits:
                for k in keys:
                    saved_song_edits[k] = edits

    # 古いコミットから新しいコミットへ順に走査
    for chash in reversed(commits):
        for rel_p in rel_draft_paths:
            d = _git_show_json(chash, rel_p)
            if not isinstance(d, dict):
                continue
            aid, norm_prd = infer_archive_id_and_period(d)
            if aid == archive_id or norm_prd == period_str:
                songs = extract_songs_list(d)
                if songs and len(songs) >= 5 and earliest_week_draft is None:
                    earliest_week_draft = d
                _harvest_from_dict(d)

    # ローカルファイル（最新の執筆スタジオ保存分）を最後に上書き適用して最優先にする
    candidate_files = [
        BACKUP_DRAFT_FILE,
        DRAFT_FILE,
        PROJECT_ROOT / "data/drafts/weekly_draft.backup.json",
        PROJECT_ROOT / "data/drafts/weekly_draft.json",
        PROJECT_ROOT / "data/weekly_draft.backup.json",
        PROJECT_ROOT / "data/weekly_draft.json",
    ]
    for path in candidate_files:
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        aid, norm_prd = infer_archive_id_and_period(data)
        if aid == archive_id or norm_prd == period_str or not aid:
            _harvest_from_dict(data)

    return earliest_week_draft, saved_song_comments, saved_song_edits, saved_meta


def get_nc_mylist_value(metrics_dict):
    if not isinstance(metrics_dict, dict):
        return 0
    val = metrics_dict.get("nc_mylist")
    if val is None:
        val = metrics_dict.get("nc_mylists", 0)
    return int(val or 0)


def calculate_song_points(song, current_metrics, prev_metrics, reference_dt):
    cur_m = current_metrics if isinstance(current_metrics, dict) and current_metrics else song
    has_prev = isinstance(prev_metrics, dict) and bool(prev_metrics)

    earliest_pub_dt = resolve_earliest_published_dt(cur_m, song, prev_metrics if has_prev else {})
    yt_pub_dt = resolve_platform_published_dt("yt", cur_m, song, prev_metrics if has_prev else {})
    nc_pub_dt = resolve_platform_published_dt("nc", cur_m, song, prev_metrics if has_prev else {})

    effective_yt_pub_dt = min(filter(None, [earliest_pub_dt, yt_pub_dt]), default=None)
    effective_nc_pub_dt = min(filter(None, [earliest_pub_dt, nc_pub_dt]), default=None)

    cur_vals = {
        "yt_views": int(cur_m.get("yt_views", 0) or 0),
        "yt_likes": int(cur_m.get("yt_likes", 0) or 0),
        "yt_comments": int(cur_m.get("yt_comments", 0) or 0),
        "nc_views": int(cur_m.get("nc_views", 0) or 0),
        "nc_mylist": get_nc_mylist_value(cur_m),
        "nc_comments": int(cur_m.get("nc_comments", 0) or 0),
    }

    raw_gains = {}
    if has_prev:
        prv_vals = {
            "yt_views": int(prev_metrics.get("yt_views", 0) or 0),
            "yt_likes": int(prev_metrics.get("yt_likes", 0) or 0),
            "yt_comments": int(prev_metrics.get("yt_comments", 0) or 0),
            "nc_views": int(prev_metrics.get("nc_views", 0) or 0),
            "nc_mylist": get_nc_mylist_value(prev_metrics),
            "nc_comments": int(prev_metrics.get("nc_comments", 0) or 0),
        }

        yt_newly_linked = prv_vals["yt_views"] == 0 and cur_vals["yt_views"] > 0
        nc_newly_linked = prv_vals["nc_views"] == 0 and cur_vals["nc_views"] > 0

        yt_new_factor = compute_new_release_factor(effective_yt_pub_dt, reference_dt)
        nc_new_factor = compute_new_release_factor(effective_nc_pub_dt, reference_dt)

        for mk in ("yt_views", "yt_likes", "yt_comments"):
            if yt_newly_linked:
                raw_gains[mk] = int(round(cur_vals[mk] * yt_new_factor))
            else:
                raw_gains[mk] = max(0, cur_vals[mk] - prv_vals[mk])

        for mk in ("nc_views", "nc_mylist", "nc_comments"):
            if nc_newly_linked:
                raw_gains[mk] = int(round(cur_vals[mk] * nc_new_factor))
            else:
                raw_gains[mk] = max(0, cur_vals[mk] - prv_vals[mk])
    else:
        yt_new_factor = compute_new_release_factor(effective_yt_pub_dt, reference_dt)
        nc_new_factor = compute_new_release_factor(effective_nc_pub_dt, reference_dt)

        for mk in ("yt_views", "yt_likes", "yt_comments"):
            raw_gains[mk] = int(round(max(0, cur_vals[mk]) * yt_new_factor))
        for mk in ("nc_views", "nc_mylist", "nc_comments"):
            raw_gains[mk] = int(round(max(0, cur_vals[mk]) * nc_new_factor))

    raw_gains["nc_mylists"] = raw_gains["nc_mylist"]

    w_yt_views = WEIGHTS.get("yt_views", 1)
    w_yt_likes = WEIGHTS.get("yt_likes", 50)
    w_yt_comments = WEIGHTS.get("yt_comments", 100)
    w_nc_views = WEIGHTS.get("nc_views", 5)
    w_nc_mylist = WEIGHTS.get("nc_mylist", WEIGHTS.get("nc_mylists", 100))
    w_nc_comments = WEIGHTS.get("nc_comments", 10)

    pts_breakdown = {
        "yt_views": raw_gains["yt_views"] * w_yt_views,
        "yt_likes": raw_gains["yt_likes"] * w_yt_likes,
        "yt_comments": raw_gains["yt_comments"] * w_yt_comments,
        "nc_views": raw_gains["nc_views"] * w_nc_views,
        "nc_mylist": raw_gains["nc_mylist"] * w_nc_mylist,
        "nc_mylists": raw_gains["nc_mylist"] * w_nc_mylist,
        "nc_comments": raw_gains["nc_comments"] * w_nc_comments,
    }

    yt_total = pts_breakdown["yt_views"] + pts_breakdown["yt_likes"] + pts_breakdown["yt_comments"]
    nc_total = pts_breakdown["nc_views"] + pts_breakdown["nc_mylist"] + pts_breakdown["nc_comments"]
    total_pt = yt_total + nc_total

    pts_breakdown["yt_total"] = yt_total
    pts_breakdown["nc_total"] = nc_total

    pub_iso_str = earliest_pub_dt.isoformat() if earliest_pub_dt else ""
    return total_pt, raw_gains, pts_breakdown, pub_iso_str


def generate_private_owner_report(draft_data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_id = draft_data.get("archiveId", "latest")
    period = draft_data.get("period", "")
    publish_at = draft_data.get("publishAt", f"{archive_id}T13:00:00+09:00")
    songs = draft_data.get("songs", [])

    lines = [
        f"# 🔒 【運営者手元用・極秘】週刊VOCALOID複合ランキング 詳細レポート",
        f"- **本番サイト解禁日時:** {publish_at} （毎週水曜 13:00 JST 自動公開）",
        f"- **集計期間:** {period}",
        f"- **ドラフト生成時刻:** {draft_data.get('updated_at', '')}",
        "",
        "---",
        "",
        "## 📊 今週の TOP 20 サマリー一覧",
        "",
        "| 順位 | 前週 | 週数 | 楽曲タイトル | ボカロP | Vocal | 総合pt | 前週比 | YT比率 / NC比率 |",
        "| :---: | :---: | :---: | :--- | :--- | :--- | ---: | :---: | :---: |",
    ]

    for s in songs:
        rank = s.get("rank", 0)
        prev = s.get("prev_rank")
        prev_str = f"{prev}位" if prev else "NEW"
        weeks = s.get("chart_in_count", 1)
        title = str(s.get("title", "")).replace("|", "｜")
        prod = str(s.get("producer", "")).replace("|", "｜")
        vocal = str(s.get("vocal", "")).replace("|", "｜")
        total_pt = int(s.get("total_pt", 0))
        ratio = f"{s.get('pt_ratio')}%" if s.get("pt_ratio") is not None else "NEW"
        yt_pt = int(s.get("yt_total_pt", 0))
        nc_pt = int(s.get("nc_total_pt", 0))
        denom = total_pt if total_pt > 0 else 1
        yt_sh = (yt_pt / denom) * 100
        nc_sh = (nc_pt / denom) * 100

        lines.append(
            f"| **{rank}位** | {prev_str} | {weeks}週 | **{title}** | {prod} | {vocal} | "
            f"**{total_pt:,} pt** | {ratio} | YT {yt_sh:.1f}% / NC {nc_sh:.1f}% |"
        )

    lines.extend(["", "---", "", "## 🔍 全20曲 6指標詳細データ（執筆リファレンス用）", ""])

    for s in songs:
        rank = s.get("rank", 0)
        raw = s.get("raw", {})
        pts = s.get("pts", {})
        total_pt = int(s.get("total_pt", 0))
        yt_pt = int(s.get("yt_total_pt", 0))
        nc_pt = int(s.get("nc_total_pt", 0))
        denom = total_pt if total_pt > 0 else 1
        yt_sh = (yt_pt / denom) * 100
        nc_sh = (nc_pt / denom) * 100
        yid = s.get("youtube_id", "")
        nid = s.get("niconico_id", "")

        lines.append(f"### {rank}位：{s.get('title')} / {s.get('producer')} （feat. {s.get('vocal')}）")
        lines.append(
            f"- **総合ポイント:** **{total_pt:,} pt** "
            f"（前週順位: {s.get('prevRank', 'NEW')} / 前週比: {s.get('pt_ratio') if s.get('pt_ratio') is not None else 'NEW'}% / {s.get('chart_in_count', 1)}週目）"
        )
        lines.append(
            f"- **YouTube計:** {yt_pt:,} pt ({yt_sh:.1f}%) ｜ "
            f"再生 +{raw.get('yt_views', 0):,} ({pts.get('yt_views', 0):,}pt) / "
            f"高評価 +{raw.get('yt_likes', 0):,} ({pts.get('yt_likes', 0):,}pt) / "
            f"コメ +{raw.get('yt_comments', 0):,} ({pts.get('yt_comments', 0):,}pt)"
        )
        lines.append(
            f"- **ニコニコ計:** {nc_pt:,} pt ({nc_sh:.1f}%) ｜ "
            f"再生 +{raw.get('nc_views', 0):,} ({pts.get('nc_views', 0):,}pt) / "
            f"マイリス +{raw.get('nc_mylist', 0):,} ({pts.get('nc_mylist', 0):,}pt) / "
            f"コメ +{raw.get('nc_comments', 0):,} ({pts.get('nc_comments', 0):,}pt)"
        )
        links = []
        if yid:
            links.append(f"YouTube: https://www.youtube.com/watch?v={yid}")
        if nid:
            links.append(f"ニコ動: https://www.nicovideo.jp/watch/{nid}")
        if links:
            lines.append(f"- **動画リンク:** {' ｜ '.join(links)}")
        lines.append("")

    report_text = "\n".join(lines)
    latest_report_path = REPORTS_DIR / "latest_private_report.md"
    dated_report_path = REPORTS_DIR / f"private_report_{archive_id}.md"

    latest_report_path.write_text(report_text, encoding="utf-8")
    dated_report_path.write_text(report_text, encoding="utf-8")

    webhook_url = os.environ.get("RANKING_NOTIFY_WEBHOOK_URL", "").strip()
    if webhook_url:
        try:
            top5_summary = "\n".join(
                [
                    f"**{s['rank']}位**: {s['title']} / {s['producer']} ({s['total_pt']:,} pt)"
                    for s in songs[:5]
                ]
            )
            msg = (
                f"📬 **【手元用通知】週刊VOCALOID複合ランキング 集計完了**\n"
                f"集計期間: `{period}`\n"
                f"本番解禁予定: `{publish_at}` (水曜13:00自動公開)\n\n"
                f"{top5_summary}\n\n"
                f"※執筆スタジオ (`python editor_server.py`) または `data/reports/latest_private_report.md` で全20曲の詳細を確認できます。"
            )
            payload = json.dumps({"content": msg, "text": msg}).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "VocaloidChartBot/1.0"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=8)
            print("[NOTIFY] Webhookへ手元用ランキング詳細通知を送信しました。")
        except Exception as e:
            print(f"[WARN] Webhook通知送信をスキップしました: {e}")

    return latest_report_path


def main():
    force_recalc = "--force" in sys.argv
    print("=== 週刊VOCALOID複合ランキング ドラフト生成・整合性チェック開始 ===")
    now_dt = datetime.now(JST)
    period_str, publish_date, archive_id, publish_at, reference_dt = compute_chart_dates(now_dt)

    # 過去週のアーカイブが欠損していればGit履歴から先に自動救出
    rescue_past_archives_from_git(current_archive_id=archive_id)

    existing_draft = load_json(DRAFT_FILE)
    if existing_draft:
        save_json(BACKUP_DRAFT_FILE, existing_draft)

    earliest_week_draft, saved_comments, saved_edits, saved_meta = find_monday_locked_draft_and_preserve_edits(
        archive_id, period_str
    )

    past_charts = collect_past_charts(exclude_archive_id=archive_id, exclude_period=period_str)
    appearance_counts, prev_chart_map = build_historical_stats(past_charts)

    # 今週の初回ドラフトが既に存在する場合は、週途中の再実行で順位やポイントが変わらないよう月曜初回ドラフトのランキングを復元・固定する
    locked_candidates = extract_songs_list(earliest_week_draft)[:TOP_N] if earliest_week_draft is not None else []
    locked_canonical = build_canonical_originals_map(locked_candidates + extract_songs_list(load_json(MASTER_FILE)))
    if (
        earliest_week_draft is not None
        and not force_recalc
        and locked_candidates
        and all(is_eligible_ranking_song(s, locked_canonical) for s in locked_candidates)
    ):
        locked_songs = locked_candidates
        for idx, s in enumerate(locked_songs, start=1):
            s["rank"] = idx
            keys = get_song_keys(s)

            # 過去チャートから正確な週数・前週順位を再照合
            past_count = 0
            prev_info = None
            for k in keys:
                if k in appearance_counts:
                    past_count = max(past_count, appearance_counts[k])
                if k in prev_chart_map and prev_info is None:
                    prev_info = prev_chart_map[k]

            if prev_info:
                s["prev_rank"] = prev_info["prev_rank"]
                s["prevRank"] = prev_info["prev_rank"]
                s["prev_total_pt"] = prev_info["prev_total_pt"]
                if prev_info["prev_total_pt"] and prev_info["prev_total_pt"] > 0:
                    s["pt_ratio"] = round((s.get("total_pt", 0) / prev_info["prev_total_pt"]) * 100)
            s["chart_in_count"] = max(int(s.get("chart_in_count") or 1), past_count + 1)

            # 執筆された解説文・表記修正を確実に反映
            for k in keys:
                if k in saved_comments:
                    s["commentary"] = saved_comments[k]
                    break
            for k in keys:
                if k in saved_edits:
                    for fld, val in saved_edits[k].items():
                        s[fld] = val
                    break

        top_songs = locked_songs
        print(
            f"[LOCKED & RESTORED] 今週分 ({archive_id}) の初回集計ドラフトを基準に順位・ポイントを固定し、"
            f"執筆済みの解説文を統合しました（1位: {top_songs[0].get('title')} / {top_songs[0].get('total_pt'):,} pt）。"
        )
    else:
        latest_snap, prev_snap = get_two_latest_snapshots()
        cur_map = extract_metrics_dict(latest_snap)
        prv_map = extract_metrics_dict(prev_snap)

        snap_list = extract_songs_list(latest_snap)
        if snap_list and snap_list[0].get("updated_at"):
            parsed_snap_dt = parse_iso_datetime(snap_list[0].get("updated_at"))
            if parsed_snap_dt:
                reference_dt = parsed_snap_dt

        master_data = load_json(MASTER_FILE)
        songs_list = extract_songs_list(master_data)
        if not songs_list:
            songs_list = snap_list
        if not songs_list and isinstance(existing_draft, dict):
            songs_list = extract_songs_list(existing_draft)

        combined_candidates = list(songs_list) + [s for s in snap_list if isinstance(s, dict)]
        canonical_map = build_canonical_originals_map(combined_candidates)

        scored_songs = []
        seen_song_keys = set()

        for song in combined_candidates:
            if not isinstance(song, dict):
                continue

            keys = get_song_keys(song)
            if not keys or (keys & seen_song_keys):
                continue
            if not is_eligible_ranking_song(song, canonical_map):
                continue

            cur_m = {}
            prv_m = {}
            for k in keys:
                if k in cur_map:
                    cur_m = cur_map[k]
                    break
            for k in keys:
                if k in prv_map:
                    prv_m = prv_map[k]
                    break

            if not cur_m and not song.get("yt_views") and not song.get("nc_views"):
                continue

            total_pt, raw_gains, pts_breakdown, resolved_pub_str = calculate_song_points(
                song, cur_m, prv_m, reference_dt
            )
            if total_pt <= 0:
                continue

            seen_song_keys.update(keys)

            past_count = 0
            prev_info = None
            for k in keys:
                if k in appearance_counts:
                    past_count = max(past_count, appearance_counts[k])
                if k in prev_chart_map and prev_info is None:
                    prev_info = prev_chart_map[k]

            prev_rank = prev_info["prev_rank"] if prev_info else None
            prev_total_pt = prev_info["prev_total_pt"] if prev_info else None

            pt_ratio = None
            if prev_total_pt is not None and prev_total_pt > 0:
                pt_ratio = round((total_pt / prev_total_pt) * 100)

            commentary = song.get("commentary") or song.get("comment") or ""
            for k in keys:
                if k in saved_comments:
                    commentary = saved_comments[k]
                    break

            yt_id = (
                song.get("youtube_id")
                or song.get("yt_id")
                or cur_m.get("youtube_id")
                or cur_m.get("yt_id")
            )
            nc_id = (
                song.get("niconico_id")
                or song.get("nc_id")
                or cur_m.get("niconico_id")
                or cur_m.get("nc_id")
            )
            primary_id = song.get("song_id") or song.get("id") or (f"song_{nc_id}" if nc_id else f"song_{yt_id}")

            title_val = cur_m.get("title") or song.get("title") or "不明な楽曲"
            prod_val = cur_m.get("producer") or song.get("producer") or "不明"
            vocal_val = cur_m.get("vocal") or song.get("vocal") or "VOCALOID"
            title_val = clean_song_title(title_val, prod_val)
            for k in keys:
                if k in saved_edits:
                    title_val = saved_edits[k].get("title", title_val)
                    prod_val = saved_edits[k].get("producer", prod_val)
                    vocal_val = saved_edits[k].get("vocal", vocal_val)
                    break

            song_entry = {
                "id": primary_id,
                "song_id": primary_id,
                "title": title_val,
                "producer": prod_val,
                "vocal": vocal_val,
                "youtube_id": yt_id,
                "niconico_id": nc_id,
                "thumbnail": (
                    song.get("thumbnail")
                    or cur_m.get("thumbnail")
                    or (f"https://i.ytimg.com/vi/{yt_id}/mqdefault.jpg" if yt_id else "")
                ),
                "published_at": resolved_pub_str or song.get("published_at") or cur_m.get("published_at") or "",
                "total_pt": total_pt,
                "yt_total_pt": pts_breakdown["yt_total"],
                "nc_total_pt": pts_breakdown["nc_total"],
                "prevRank": prev_rank if prev_rank is not None else "NEW",
                "prev_rank": prev_rank,
                "prev_total_pt": prev_total_pt,
                "pt_ratio": pt_ratio,
                "_past_chart_in_count": past_count,
                "raw": raw_gains,
                "pts": pts_breakdown,
                "commentary": commentary,
            }
            if not is_eligible_ranking_song(song_entry, canonical_map):
                continue
            scored_songs.append(song_entry)

        scored_songs.sort(key=lambda x: (-x["total_pt"], str(x.get("song_id", ""))))
        top_songs = scored_songs[:TOP_N]

        for idx, item in enumerate(top_songs, start=1):
            item["rank"] = idx
            past_c = item.pop("_past_chart_in_count", 0)
            item["chart_in_count"] = past_c + 1

    now_str = now_dt.strftime("%Y-%m-%d %H:%M")
    weekly_summary = (
        saved_meta.get("weeklySummary")
        or saved_meta.get("overall_commentary")
        or (existing_draft.get("weeklySummary", "") if isinstance(existing_draft, dict) else "")
        or (existing_draft.get("overall_commentary", "") if isinstance(existing_draft, dict) else "")
    )
    trend_analysis = (
        saved_meta.get("trend_analysis")
        or (existing_draft.get("trend_analysis", "") if isinstance(existing_draft, dict) else "")
    )

    draft_output = {
        "publishDate": publish_date,
        "publishAt": publish_at,
        "archiveId": archive_id,
        "period": period_str,
        "updated_at": now_str,
        "weeklySummary": weekly_summary,
        "overall_commentary": weekly_summary,
        "trend_analysis": trend_analysis,
        "weights": WEIGHTS,
        "songs": top_songs,
        "ranking": top_songs,
    }

    save_json(DRAFT_FILE, draft_output)
    save_json(BACKUP_DRAFT_FILE, draft_output)

    alt_draft = PROJECT_ROOT / "data" / "weekly_draft.json"
    if alt_draft.resolve() != DRAFT_FILE.resolve():
        save_json(alt_draft, draft_output)

    report_path = generate_private_owner_report(draft_output)

    print(
        f"[OK] TOP {len(top_songs)} のドラフトを手元用に生成しました: {DRAFT_FILE}\n"
        f"     集計期間: {period_str} / 本番サイト解禁予定: {publish_at} (水曜13:00)\n"
        f"     手元用詳細レポート: {report_path}"
    )


if __name__ == "__main__":
    main()