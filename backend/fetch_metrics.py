import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta, timezone
from config import BASE_DIR, MASTER_FILE, PREV_SNAPSHOT, LATEST_SNAPSHOT
from discover_songs import search_youtube_id_web_strict
from vocaloid_filter import build_canonical_originals_map, clean_song_title, detect_vocals, is_eligible_ranking_song
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

USER_AGENT = "Mozilla/5.0 (compatible; VocaloidCombinedChartBot/8.2)"
JST = timezone(timedelta(hours=9))


def get_monday_date_str(dt_str: str) -> str:
    """ISO日時文字列から、その日時が属する週の月曜日の日付(YYYY-MM-DD)を返す"""
    if not dt_str:
        return ""
    try:
        cleaned = dt_str.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        else:
            dt = dt.astimezone(JST)
        d = dt.date()
        monday = d - timedelta(days=d.weekday())
        return monday.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _git_log_commits(rel_path: str, max_count: int = 40) -> list:
    try:
        res = subprocess.run(
            ["git", "log", f"-n{max_count}", "--format=%H", "--", rel_path],
            cwd=BASE_DIR,
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
            cwd=BASE_DIR,
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


def restore_and_lock_monday_snapshot_if_same_week(force_refresh: bool = False) -> bool:
    """
    【週次スナップショット完全ロック＆Git履歴からの月曜データ自動復元機構】
    1. Git履歴を走査し、今週（now_monday_str）に記録された最も古い（＝月曜本来の）latest_monday.json と、
       前週以前の最新のスナップショット（prev_monday.json用）を特定する。
    2. もし週の途中（水曜など）の再実行で latest_monday.json が上書きされていた場合は、
       月曜時点のスナップショットへ自動的に巻き戻す。
    3. 今週分のスナップショットが既に存在する場合は True を返し、週途中の再取得によるポイント変動を完全に防止する。
    """
    now_monday_str = get_monday_date_str(datetime.now(JST).isoformat())
    rel_latest = "data/snapshots/latest_monday.json"
    commits = _git_log_commits(rel_latest, max_count=40)

    earliest_this_week_snap = None
    earliest_this_week_ts = ""
    latest_prev_week_snap = None
    latest_prev_week_monday = ""

    # 古いコミットから順に走査して「今週最初のスナップショット」と「前週以前のスナップショット」を特定
    for chash in reversed(commits):
        snap_data = _git_show_json(chash, rel_latest)
        if not isinstance(snap_data, list) or len(snap_data) < 5:
            continue
        upd_str = snap_data[0].get("updated_at", "")
        snap_monday = get_monday_date_str(upd_str)
        if not snap_monday:
            continue

        if snap_monday == now_monday_str:
            if earliest_this_week_snap is None:
                earliest_this_week_snap = snap_data
                earliest_this_week_ts = upd_str
        elif snap_monday < now_monday_str:
            latest_prev_week_snap = snap_data
            latest_prev_week_monday = snap_monday

    # 前週スナップショットの保護・復元
    if latest_prev_week_snap is not None:
        need_prev_restore = not PREV_SNAPSHOT.exists()
        if not need_prev_restore:
            try:
                cur_prev = json.loads(PREV_SNAPSHOT.read_text(encoding="utf-8"))
                if not isinstance(cur_prev, list) or len(cur_prev) < 5:
                    need_prev_restore = True
                else:
                    pm = get_monday_date_str(cur_prev[0].get("updated_at", ""))
                    if pm >= now_monday_str:
                        need_prev_restore = True
            except Exception:
                need_prev_restore = True

        if need_prev_restore:
            PREV_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            with open(PREV_SNAPSHOT, "w", encoding="utf-8") as f:
                json.dump(latest_prev_week_snap, f, ensure_ascii=False, indent=2)
            print(f"[RESTORE] Git履歴から前週スナップショット ({latest_prev_week_monday}週) を prev_monday.json に復元しました。")

    # 今週の月曜スナップショットがGit履歴に存在する場合、週途中の上書きがあれば月曜時点に巻き戻してロックする
    if earliest_this_week_snap is not None and not force_refresh:
        LATEST_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        cur_ts = ""
        if LATEST_SNAPSHOT.exists():
            try:
                cur_latest = json.loads(LATEST_SNAPSHOT.read_text(encoding="utf-8"))
                if isinstance(cur_latest, list) and cur_latest:
                    cur_ts = cur_latest[0].get("updated_at", "")
            except Exception:
                pass

        if cur_ts != earliest_this_week_ts:
            with open(LATEST_SNAPSHOT, "w", encoding="utf-8") as f:
                json.dump(earliest_this_week_snap, f, ensure_ascii=False, indent=2)
            print(
                f"[RESTORE & LOCK] 週の途中で再取得されたスナップショット({cur_ts})を検知したため、"
                f"今週初回取得時({earliest_this_week_ts})のデータへ自動復元しました。"
            )
        else:
            print(
                f"[LOCKED] 今週分 ({now_monday_str}週 / 取得日時: {earliest_this_week_ts}) のスナップショットは確定済みのため、"
                f"数値変動を防ぐため再取得をスキップして月曜時点のデータを維持します。"
            )
        return True

    # Git未コミットだがローカルに今週分がある場合も保護
    if LATEST_SNAPSHOT.exists() and not force_refresh:
        try:
            with open(LATEST_SNAPSHOT, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) >= 5:
                updated_str = data[0].get("updated_at", "")
                last_monday_str = get_monday_date_str(updated_str)
                if last_monday_str == now_monday_str:
                    print(f"[LOCKED] 同一週 ({now_monday_str}週) のスナップショットが既に存在するため、再取得をスキップします。")
                    return True
                elif last_monday_str and last_monday_str < now_monday_str:
                    PREV_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(LATEST_SNAPSHOT, PREV_SNAPSHOT)
                    print(f"前週のスナップショット ({last_monday_str}週) を prev_monday.json にローテーションしました。")
        except Exception as e:
            print(f"Snapshot rotation check skipped: {e}")

    return False


def fetch_youtube_stats_batch(youtube_ids: list, api_key: str) -> dict:
    result = {}
    if not api_key or not youtube_ids:
        return result

    youtube = build("youtube", "v3", developerKey=api_key)
    valid_ids = list(dict.fromkeys([yid for yid in youtube_ids if yid]))

    for i in range(0, len(valid_ids), 50):
        chunk = valid_ids[i:i + 50]
        for attempt in range(2):
            try:
                res = youtube.videos().list(
                    part="snippet,statistics",
                    id=",".join(chunk)
                ).execute()
                for item in res.get("items", []):
                    vid = item["id"]
                    stats = item.get("statistics", {})
                    snippet = item.get("snippet", {})
                    result[vid] = {
                        "yt_title": snippet.get("title", ""),
                        "yt_desc": snippet.get("description", "")[:400],
                        "yt_tags": " ".join(snippet.get("tags", [])),
                        "yt_views": int(stats.get("viewCount", 0)),
                        "yt_likes": int(stats.get("likeCount", 0)),
                        "yt_comments": int(stats.get("commentCount", 0)),
                        "yt_published_at": snippet.get("publishedAt", ""),
                        "channel_title": snippet.get("channelTitle", "")
                    }
                break
            except Exception as e:
                print(f"YouTube Batch API Warning (attempt {attempt + 1}): {e}")
                time.sleep(1)
    return result


def fetch_niconico_thumbinfo(niconico_id: str) -> dict:
    if not niconico_id:
        return {}
    url = f"https://ext.nicovideo.jp/api/getthumbinfo/{niconico_id}"
    for attempt in range(2):
        try:
            res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
            root = ET.fromstring(res.text)
            if root.attrib.get("status") == "ok":
                thumb = root.find("thumb")
                tags = " ".join([t.text for t in thumb.findall("tags/tag") if t.text])
                return {
                    "nc_title": thumb.findtext("title", ""),
                    "nc_desc": (thumb.findtext("description", "") or "")[:400],
                    "nc_tags": tags,
                    "nc_views": int(thumb.findtext("view_counter", "0")),
                    "nc_mylist": int(thumb.findtext("mylist_counter", "0")),
                    "nc_comments": int(thumb.findtext("comment_num", "0")),
                    "nc_published_at": thumb.findtext("first_retrieve", ""),
                    "nc_author": thumb.findtext("user_nickname", "")
                }
        except Exception:
            time.sleep(0.4)
    return {}


def fetch_niconico_stats_hybrid(niconico_ids: list) -> dict:
    result = {}
    valid_ids = list(dict.fromkeys([nid for nid in niconico_ids if nid]))
    if not valid_ids:
        return result

    snap_url = "https://api.search.nicovideo.jp/api/v2/snapshot/video/contents/search"
    headers = {"User-Agent": USER_AGENT}

    for i in range(0, len(valid_ids), 40):
        chunk = valid_ids[i:i + 40]
        params = {
            "q": "",
            "targets": "",
            "fields": "contentId,title,description,tags,viewCounter,mylistCounter,commentCounter,startTime",
            "_sort": "-viewCounter",
            "_limit": len(chunk),
            "_context": "VocaloidCombinedChartBot"
        }
        for idx, cid in enumerate(chunk):
            params[f"filters[contentId][{idx}]"] = cid
        try:
            res = requests.get(snap_url, params=params, headers=headers, timeout=12)
            if res.status_code == 200:
                for item in res.json().get("data", []):
                    cid = item.get("contentId")
                    result[cid] = {
                        "nc_title": item.get("title", ""),
                        "nc_desc": (item.get("description") or "")[:400],
                        "nc_tags": item.get("tags", ""),
                        "nc_views": int(item.get("viewCounter", 0)),
                        "nc_mylist": int(item.get("mylistCounter", 0)),
                        "nc_comments": int(item.get("commentCounter", 0)),
                        "nc_published_at": item.get("startTime", ""),
                        "nc_author": ""
                    }
        except Exception:
            pass

    for cid in valid_ids:
        if cid not in result or result[cid]["nc_views"] == 0 or not result[cid].get("nc_published_at"):
            info = fetch_niconico_thumbinfo(cid)
            if info:
                result[cid] = info

    return result


def pick_earliest_iso(dt_str1: str, dt_str2: str, dt_str3: str = "") -> str:
    """複数の公開日時文字列のうち、最も古い（本来の初出）日時文字列を返す"""
    valid = [s.strip() for s in (dt_str1, dt_str2, dt_str3) if s and str(s).strip()]
    if not valid:
        return ""
    return min(valid)


def main():
    force_refresh = "--force" in sys.argv
    if restore_and_lock_monday_snapshot_if_same_week(force_refresh=force_refresh):
        return

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("エラー: YOUTUBE_API_KEY が設定されていません。")
        return

    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        songs = json.load(f)
    canonical_map = build_canonical_originals_map(songs)

    yt_ids = [s.get("youtube_id") for s in songs if s.get("youtube_id")]
    nc_ids = [s.get("niconico_id") for s in songs if s.get("niconico_id")]

    yt_map = fetch_youtube_stats_batch(yt_ids, api_key)
    nc_map = fetch_niconico_stats_hybrid(nc_ids)

    used_yt_ids = set(yt_ids)
    rescue_yt_ids = []
    for song in songs:
        yid = song.get("youtube_id", "")
        nid = song.get("niconico_id", "")
        nc_v = nc_map.get(nid, {}).get("nc_views", 0)
        if (not yid or yid not in yt_map) and nc_v >= 10000:
            found_yid = search_youtube_id_web_strict(song["title"], song["producer"], used_yt_ids)
            if found_yid and found_yid not in used_yt_ids:
                song["youtube_id"] = found_yid
                used_yt_ids.add(found_yid)
                rescue_yt_ids.append(found_yid)

    if rescue_yt_ids:
        yt_map.update(fetch_youtube_stats_batch(rescue_yt_ids, api_key))
        with open(MASTER_FILE, "w", encoding="utf-8") as f:
            json.dump(songs, f, ensure_ascii=False, indent=2)

    snapshots = []
    seen_yt = set()
    seen_nc = set()
    now_iso = datetime.now(JST).isoformat()

    for song in songs:
        sid = song["song_id"]
        yid = song.get("youtube_id", "")
        nid = song.get("niconico_id", "")

        if (yid and yid in seen_yt) or (nid and nid in seen_nc):
            continue
        if yid:
            seen_yt.add(yid)
        if nid:
            seen_nc.add(nid)

        yt_stats = yt_map.get(yid, {})
        nc_stats = nc_map.get(nid, {})

        yt_views = yt_stats.get("yt_views", 0)
        yt_likes = yt_stats.get("yt_likes", 0)
        yt_comments = yt_stats.get("yt_comments", 0)

        nc_views = nc_stats.get("nc_views", 0)
        nc_mylist = nc_stats.get("nc_mylist", 0)
        nc_comments = nc_stats.get("nc_comments", 0)

        if yt_views == 0 and nc_views == 0:
            continue

        producer = song.get("producer") or nc_stats.get("nc_author") or yt_stats.get("channel_title") or "ボカロP"
        title = clean_song_title(song["title"], producer)
        if title.lower() == producer.lower() or len(title) <= 1:
            raw_t = yt_stats.get("yt_title") or nc_stats.get("nc_title") or song["title"]
            title = clean_song_title(raw_t, producer)

        video_titles = f"{yt_stats.get('yt_title', '')} {nc_stats.get('nc_title', '')}".strip()
        video_metas = " ".join([
            yt_stats.get("yt_tags", ""),
            yt_stats.get("yt_desc", ""),
            nc_stats.get("nc_tags", ""),
            nc_stats.get("nc_desc", "")
        ]).strip()
        vocal = detect_vocals(video_titles, video_metas, song.get("vocal", ""))

        yt_pub = yt_stats.get("yt_published_at", "")
        nc_pub = nc_stats.get("nc_published_at", "")
        earliest_pub = pick_earliest_iso(yt_pub, nc_pub, song.get("published_at", ""))

        song_entry = {
            "song_id": sid,
            "title": title,
            "producer": producer,
            "vocal": vocal,
            "youtube_id": yid,
            "niconico_id": nid,
            "published_at": earliest_pub,
            "yt_published_at": yt_pub,
            "nc_published_at": nc_pub,
            "yt_views": yt_views,
            "yt_likes": yt_likes,
            "yt_comments": yt_comments,
            "nc_views": nc_views,
            "nc_mylist": nc_mylist,
            "nc_comments": nc_comments,
            "updated_at": now_iso
        }
        if not is_eligible_ranking_song(song_entry, canonical_map):
            continue
        snapshots.append(song_entry)

    LATEST_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    with open(LATEST_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, ensure_ascii=False, indent=2)
    print(f"全 {len(snapshots)} 曲の6指標データ取得が完了しました。")


if __name__ == "__main__":
    main()