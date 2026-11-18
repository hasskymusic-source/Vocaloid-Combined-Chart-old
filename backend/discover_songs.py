import json
import os
from datetime import datetime, timedelta, timezone

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

from config import MASTER_FILE, LATEST_SNAPSHOT
from discovery_sources import (
    crawl_active_producer_channels_rss, crawl_niconico_comprehensive, crawl_vocadb_global_and_domestic,
    crawl_youtube_multilingual_zero_quota, get_niconico_thumbinfo, lookup_vocadb_by_pv,
    search_niconico_id_snapshot_strict, search_youtube_id_web_strict,
)
from vocaloid_dict import DERIVATIVE_CHARACTERS, NC_ID_PATTERN, YT_ID_PATTERN
from vocaloid_filter import (
    VOCAL_NORM_SET, build_canonical_originals_map, clean_song_title, detect_vocals,
    is_eligible_ranking_song, is_valid_vocaloid_mv, normalize_compare_str, normalize_match_key, parse_iso_duration_seconds,
)

JST = timezone(timedelta(hours=9))


def _parse_dt_safe(dt_str: str):
    cleaned = str(dt_str or "").strip()
    if not cleaned:
        return None
    try:
        dt = datetime.fromisoformat(cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned)
        return (dt.replace(tzinfo=JST) if dt.tzinfo is None else dt).astimezone(JST)
    except Exception:
        return None


def _is_partial_title_match(entry_vocal: str, entry_pub: str, target: dict) -> bool:
    v1 = {v.strip() for v in (entry_vocal or "").split("・") if v.strip()}
    v2 = {v.strip() for v in (target.get("vocal") or "").split("・") if v.strip()}
    if not ((v1 & v2) or "VOCALOID" in v1 or "VOCALOID" in v2):
        return False
    dt1, dt2 = _parse_dt_safe(entry_pub), _parse_dt_safe(target.get("published_at", ""))
    if dt1 is None or dt2 is None:
        return False
    return abs((dt1 - dt2).total_seconds()) <= 3.0 * 86400.0


def verify_and_purge_existing_pool(youtube, raw_items: list) -> tuple:
    canonical_map = build_canonical_originals_map(raw_items)
    yt_ids = list(dict.fromkeys([x.get("youtube_id") for x in raw_items if x.get("youtube_id")]))
    yt_meta = {}
    for i in range(0, len(yt_ids), 50):
        try:
            res = youtube.videos().list(part="snippet,contentDetails", id=",".join(yt_ids[i:i + 50])).execute()
            for item in res.get("items", []):
                yt_meta[item["id"]] = item
        except Exception:
            pass

    verified, channel_scores = [], {}
    for item in raw_items:
        yid, nid, title = (item.get("youtube_id") or "").strip(), (item.get("niconico_id") or "").strip(), item.get("title", "")
        nc_title_str, nc_meta_str, nc_pub_str, nc_valid = "", "", "", False
        if nid and (nc_info := get_niconico_thumbinfo(nid)):
            if not is_valid_vocaloid_mv(nc_info["title"], nc_info["description"], nc_info["tags"], nc_info["duration_sec"], is_niconico=True, producer=nc_info.get("producer") or item.get("producer", "")):
                continue
            nc_valid = True
            nc_title_str, nc_meta_str, nc_pub_str = nc_info["title"], f"{nc_info['tags']} {nc_info['description'][:300]}", nc_info.get("published_at", "")

        yt_title_str, yt_meta_str, yt_pub_str, ch_id = "", "", "", ""
        if yid and yid in yt_meta:
            snippet = yt_meta[yid].get("snippet", {})
            dur_sec = parse_iso_duration_seconds(yt_meta[yid].get("contentDetails", {}).get("duration", ""))
            y_title, y_desc, y_tags, y_channel = snippet.get("title", ""), snippet.get("description", ""), " ".join(snippet.get("tags", [])), snippet.get("channelTitle", "")
            yt_pub_str, ch_id = snippet.get("publishedAt", ""), snippet.get("channelId", "")
            yt_valid = is_valid_vocaloid_mv(y_title, y_desc, y_tags, dur_sec, is_niconico=False, yt_category_id=snippet.get("categoryId", "10"), producer=y_channel or item.get("producer", ""), has_niconico=bool(nid))
            if not yt_valid:
                if nc_valid:
                    vdb = lookup_vocadb_by_pv("NicoNicoDouga", nid)
                    if not vdb.get("rejected") and vdb.get("youtube_id") == yid:
                        yt_valid = True
                    else:
                        item["youtube_id"] = ""
                        yid = ""
                else:
                    continue
            if yt_valid:
                yt_title_str, yt_meta_str = y_title, f"{y_tags} {y_desc[:300]}"
                if nid and title:
                    norm_t, norm_yt = normalize_compare_str(title), normalize_compare_str(y_title)
                    if len(norm_t) >= 2 and norm_t not in norm_yt and norm_yt not in norm_t:
                        vdb = lookup_vocadb_by_pv("NicoNicoDouga", nid)
                        if vdb.get("rejected") or vdb.get("youtube_id") != yid:
                            item["youtube_id"] = ""
                            yid = ""

        combined_titles, combined_metas = f"{yt_title_str} {nc_title_str}".strip(), f"{yt_meta_str} {nc_meta_str}".strip()
        if combined_titles or combined_metas:
            item["vocal"] = detect_vocals(combined_titles, combined_metas, item.get("vocal", ""))
        pub_candidates = [s for s in (item.get("published_at", ""), item.get("yt_published_at", ""), item.get("nc_published_at", ""), yt_pub_str, nc_pub_str) if s and str(s).strip()]
        if pub_candidates:
            item["published_at"] = min(pub_candidates)
        if is_eligible_ranking_song(item, canonical_map):
            verified.append(item)
            if ch_id and yid:
                channel_scores[ch_id] = channel_scores.get(ch_id, 0) + (3 if nid else 1)

    active_channels = [cid for cid, _ in sorted(channel_scores.items(), key=lambda x: x[1], reverse=True)[:80]]
    return verified, active_channels


def upsert_song_into_pool(entry: dict, pool: list, by_yt: dict, by_nc: dict, by_tp: dict, by_title_partial: dict):
    """既存プールへの重複統合・片側欠損の安全名寄せ・新規追加を行う"""
    yid, nid = (entry.get("youtube_id") or "").strip(), (entry.get("niconico_id") or "").strip()
    title = clean_song_title(entry.get("title", ""), entry.get("producer", ""))
    producer, vocal = (entry.get("producer") or "ボカロP").strip(), entry.get("vocal") or "VOCALOID"
    pub_at = (entry.get("published_at") or entry.get("yt_published_at") or entry.get("nc_published_at") or "").strip()
    if not yid and not nid:
        return
    t_key, p_key = normalize_match_key(title), normalize_match_key(producer)
    tp_key = f"{t_key}::{p_key}" if (t_key and p_key) else ""

    target = by_nc.get(nid) if (nid and nid in by_nc) else (by_yt.get(yid) if (yid and yid in by_yt) else by_tp.get(tp_key))
    if target is None and bool(yid) != bool(nid) and len(t_key) >= 4 and t_key not in VOCAL_NORM_SET:
        for cand in by_title_partial.get(t_key, []):
            has_comp = (bool(yid) and not cand.get("youtube_id") and bool(cand.get("niconico_id"))) or (bool(nid) and not cand.get("niconico_id") and bool(cand.get("youtube_id")))
            if has_comp and _is_partial_title_match(vocal, pub_at, cand):
                target = cand
                break

    if target is not None:
        if yid and not target.get("youtube_id") and yid not in by_yt: target["youtube_id"] = yid; by_yt[yid] = target
        if nid and not target.get("niconico_id") and nid not in by_nc: target["niconico_id"] = nid; by_nc[nid] = target
        if title and (not target.get("title") or target["title"] == target.get("producer")): target["title"] = title
        if producer and producer != "ボカロP" and target.get("producer") == "ボカロP": target["producer"] = producer
        if vocal and vocal != "VOCALOID" and (target.get("vocal") in ["", "VOCALOID", "VOCALOID / 合成音声"] or any(d in vocal for d in DERIVATIVE_CHARACTERS)):
            target["vocal"] = vocal
        if pub_at:
            target["published_at"] = min(target.get("published_at", ""), pub_at) if target.get("published_at") else pub_at
        return

    yid = "" if yid in by_yt else yid
    nid = "" if nid in by_nc else nid
    if not yid and not nid:
        return
    new_item = {
        "song_id": entry.get("song_id") or f"song_{nid or yid}", "title": title or "Unknown",
        "producer": producer, "vocal": vocal, "youtube_id": yid, "niconico_id": nid, "published_at": pub_at,
    }
    pool.append(new_item)
    if yid: by_yt[yid] = new_item
    if nid: by_nc[nid] = new_item
    if tp_key: by_tp[tp_key] = new_item
    if len(t_key) >= 4 and t_key not in VOCAL_NORM_SET:
        by_title_partial.setdefault(t_key, []).append(new_item)


def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key or build is None:
        print("エラー: YOUTUBE_API_KEY または googleapiclient が利用できません。")
        return

    youtube = build("youtube", "v3", developerKey=api_key)
    raw_loaded = []
    for path in [MASTER_FILE, LATEST_SNAPSHOT]:
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    raw_loaded.extend(loaded)
            except Exception:
                pass

    pool, by_yt, by_nc, by_tp, by_title_partial = [], {}, {}, {}, {}
    verified_existing, active_channels = verify_and_purge_existing_pool(youtube, raw_loaded)
    for item in verified_existing:
        upsert_song_into_pool(item, pool, by_yt, by_nc, by_tp, by_title_partial)

    canonical_map = build_canonical_originals_map(pool)
    for v_item in crawl_vocadb_global_and_domestic():
        if is_eligible_ranking_song(v_item, canonical_map):
            upsert_song_into_pool(v_item, pool, by_yt, by_nc, by_tp, by_title_partial)

    for cid in [c for c in crawl_niconico_comprehensive() if c not in by_nc]:
        nc_info = get_niconico_thumbinfo(cid)
        if not nc_info or not is_valid_vocaloid_mv(nc_info["title"], nc_info["description"], nc_info["tags"], nc_info["duration_sec"], is_niconico=True, producer=nc_info.get("producer", "")):
            continue
        vdb = lookup_vocadb_by_pv("NicoNicoDouga", cid)
        if vdb.get("rejected"):
            continue
        producer = vdb.get("producer") or nc_info["producer"] or "ボカロP"
        title = vdb.get("title") or clean_song_title(nc_info["title"], producer)
        vocal = detect_vocals(nc_info["title"], f"{nc_info['tags']} {nc_info['description'][:300]}", vdb.get("vocal", ""))
        yt_id = vdb.get("youtube_id", "") or (YT_ID_PATTERN.search(nc_info["description"]).group(1) if YT_ID_PATTERN.search(nc_info["description"]) else "")
        cand = {"song_id": f"song_{cid}", "title": title, "producer": producer, "vocal": vocal, "youtube_id": yt_id, "niconico_id": cid, "published_at": nc_info.get("published_at") or vdb.get("published_at", "")}
        if is_eligible_ranking_song(cand, canonical_map):
            upsert_song_into_pool(cand, pool, by_yt, by_nc, by_tp, by_title_partial)

    canonical_map = build_canonical_originals_map(pool)
    yt_candidates = list(dict.fromkeys(crawl_youtube_multilingual_zero_quota() + crawl_active_producer_channels_rss(active_channels)))
    new_yt_ids = [vid for vid in yt_candidates if vid not in by_yt]
    for i in range(0, len(new_yt_ids), 50):
        try:
            v_res = youtube.videos().list(part="snippet,contentDetails", id=",".join(new_yt_ids[i:i + 50])).execute()
            for item in v_res.get("items", []):
                vid, snippet = item["id"], item.get("snippet", {})
                dur_sec = parse_iso_duration_seconds(item.get("contentDetails", {}).get("duration", ""))
                raw_title, desc, tags, channel = snippet.get("title", ""), snippet.get("description", ""), " ".join(snippet.get("tags", [])), snippet.get("channelTitle", "ボカロP")
                if not is_valid_vocaloid_mv(raw_title, desc, tags, dur_sec, is_niconico=False, yt_category_id=snippet.get("categoryId", "10"), producer=channel):
                    continue
                vdb = lookup_vocadb_by_pv("Youtube", vid)
                if vdb.get("rejected"):
                    continue
                producer = vdb.get("producer") or channel
                title = vdb.get("title") or clean_song_title(raw_title, producer)
                vocal = detect_vocals(raw_title, f"{tags} {desc[:300]}", vdb.get("vocal", ""))
                nc_id = vdb.get("niconico_id", "") or (NC_ID_PATTERN.search(desc).group(1) if NC_ID_PATTERN.search(desc) else "")
                cand = {"song_id": f"song_{nc_id or vid}", "title": title, "producer": producer, "vocal": vocal, "youtube_id": vid, "niconico_id": nc_id, "published_at": vdb.get("published_at") or snippet.get("publishedAt", "")}
                if is_eligible_ranking_song(cand, canonical_map):
                    upsert_song_into_pool(cand, pool, by_yt, by_nc, by_tp, by_title_partial)
        except Exception as e:
            print(f"YouTube batch check error: {e}")

    repaired_count = 0
    incomplete = sorted([s for s in pool if bool(s.get("youtube_id")) != bool(s.get("niconico_id"))], key=lambda x: str(x.get("published_at") or ""), reverse=True)[:120]
    for song in incomplete:
        yid, nid = song.get("youtube_id", ""), song.get("niconico_id", "")
        if nid and not yid:
            vdb = lookup_vocadb_by_pv("NicoNicoDouga", nid)
            cand_yid = "" if vdb.get("rejected") else vdb.get("youtube_id", "")
            if not cand_yid and (nc_info := get_niconico_thumbinfo(nid)) and (m := YT_ID_PATTERN.search(nc_info["description"])):
                cand_yid = m.group(1)
            if not cand_yid and song.get("title"):
                cand_yid = search_youtube_id_web_strict(song["title"], song["producer"], set(by_yt.keys()))
            if cand_yid and cand_yid not in by_yt:
                song["youtube_id"] = cand_yid; by_yt[cand_yid] = song; repaired_count += 1
        elif yid and not nid:
            vdb = lookup_vocadb_by_pv("Youtube", yid)
            cand_nid = "" if vdb.get("rejected") else vdb.get("niconico_id", "")
            if not cand_nid and song.get("title"):
                cand_nid = search_niconico_id_snapshot_strict(song["title"], song["producer"], set(by_nc.keys()))
            if cand_nid and cand_nid not in by_nc:
                song["niconico_id"] = cand_nid; by_nc[cand_nid] = song; repaired_count += 1

    final_canonical = build_canonical_originals_map(pool)
    pool = [s for s in pool if is_eligible_ranking_song(s, final_canonical)]
    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    both_paired = sum(1 for s in pool if s.get("youtube_id") and s.get("niconico_id"))
    print(f"厳格検証プール更新完了: 全 {len(pool)} 曲 (両サイトペア済: {both_paired} 曲 / 新規補完: {repaired_count} 曲)")


if __name__ == "__main__":
    main()
