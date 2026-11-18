import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import requests

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

from config import MASTER_FILE, LATEST_SNAPSHOT
from vocaloid_filter import (
    DERIVATIVE_CHARACTERS, NC_ID_PATTERN, NG_KEYWORDS, NG_PRODUCER_KEYWORDS, YT_ID_PATTERN,
    build_canonical_originals_map, clean_song_title, detect_vocals, extract_vocadb_song_info,
    is_eligible_ranking_song, is_valid_vocaloid_mv, normalize_compare_str, normalize_match_key, parse_iso_duration_seconds,
)

USER_AGENT = "Mozilla/5.0 (compatible; VocaloidCombinedChartBot/8.2)"
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def lookup_vocadb_by_pv(service: str, pv_id: str) -> dict:
    if not pv_id:
        return {}
    try:
        res = requests.get(
            "https://vocadb.net/api/songs/byPv",
            params={"pvService": service, "pvId": pv_id, "fields": "PVs,Artists", "lang": "Japanese"},
            headers={"User-Agent": USER_AGENT}, timeout=8,
        )
        if res.status_code == 200 and res.text and res.text != "null":
            return extract_vocadb_song_info(res.json())
    except Exception:
        pass
    return {}


def crawl_vocadb_global_and_domestic() -> list:
    results, now = [], datetime.now(timezone.utc)
    for days in [14, 45, 120, 365]:
        params = {
            "songTypes": "Original", "afterDate": (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z"),
            "sort": "RatingScore", "maxResults": 50, "fields": "PVs,Artists", "lang": "Japanese",
        }
        try:
            res = requests.get("https://vocadb.net/api/songs", params=params, headers={"User-Agent": USER_AGENT}, timeout=12)
            if res.status_code == 200:
                for item in res.json().get("items", []):
                    info = extract_vocadb_song_info(item)
                    if info and not info.get("rejected") and (info.get("youtube_id") or info.get("niconico_id")) and is_eligible_ranking_song(info):
                        results.append(info)
        except Exception as e:
            print(f"VocaDB window({days}d) fetch warning: {e}")
    print(f"VocaDB グローバル＆国内トレンド収集: {len(results)} 件取得")
    return results


def crawl_niconico_comprehensive() -> list:
    nc_ids, headers = [], {"User-Agent": USER_AGENT}
    rss_urls = [
        "https://www.nicovideo.jp/tag/VOCALOID?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/VOCALOID?sort=f&order=d&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%9C%E3%82%AB%E3%83%AD%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%9F%E3%82%AF%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%86%E3%83%88%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/SynthesizerV%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
    ]
    for r_url in rss_urls:
        try:
            res = requests.get(r_url, headers=headers, timeout=10)
            if res.status_code == 200:
                nc_ids.extend(cid for cid in NC_ID_PATTERN.findall(res.text) if cid not in nc_ids)
        except Exception:
            pass

    snap_url, now = "https://api.search.nicovideo.jp/api/v2/snapshot/video/contents/search", datetime.now(timezone.utc)
    snap_plans = [
        {"_sort": s, "filters[startTime][gte]": (now - timedelta(days=d)).strftime("%Y-%m-%dT00:00:00+09:00"), "_limit": 50}
        for s, d in [("-mylistCounter", 7), ("-viewCounter", 7), ("-mylistCounter", 14), ("-viewCounter", 35), ("-viewCounter", 120)]
    ]
    for sp in snap_plans:
        params = {"q": "VOCALOID OR ボカロオリジナル曲 OR SynthesizerVオリジナル曲 OR テトオリジナル曲", "targets": "tagsExact", "fields": "contentId", "_context": "VocaloidCombinedChartBot", **sp}
        try:
            res = requests.get(snap_url, params=params, headers=headers, timeout=10)
            if res.status_code == 200:
                for item in res.json().get("data", []):
                    if (cid := item.get("contentId")) and cid not in nc_ids:
                        nc_ids.append(cid)
        except Exception:
            pass
    print(f"ニコニコ動画 マルチ期間トレンド収集: {len(nc_ids)} 件取得")
    return nc_ids[:160]


def search_youtube_id_web_strict(target_title: str, target_producer: str, existing_yt_ids: set) -> str:
    norm_title, norm_prod, p_key = normalize_compare_str(target_title), normalize_compare_str(target_producer), normalize_match_key(target_producer)
    if len(norm_title) < 2:
        return ""
    headers = {"User-Agent": CHROME_UA, "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"}
    try:
        res = requests.get("https://www.youtube.com/results", params={"search_query": f'"{target_title}" {target_producer} MV'}, headers=headers, timeout=10)
        if res.status_code != 200:
            return ""
        for m in list(re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', res.text))[:5]:
            vid = m.group(1)
            if vid in existing_yt_ids:
                continue
            block = res.text[m.start():m.start() + 4000]
            t_m = re.search(r'"title":\{"runs":\[\{"text":"([^"]+)"', block)
            if not t_m:
                continue
            vtitle = t_m.group(1)
            o_m = re.search(r'"(?:ownerText|longBylineText)":\{"runs":\[\{"text":"([^"]+)"', block)
            owner = o_m.group(1) if o_m else ""
            v_low, o_low = vtitle.lower(), owner.lower()
            if any(ng in v_low for ng in NG_KEYWORDS) or any(ng_p in v_low or ng_p in o_low for ng_p in NG_PRODUCER_KEYWORDS):
                continue
            norm_vtitle = normalize_compare_str(vtitle)
            if norm_title not in norm_vtitle:
                continue
            vt_key, owner_key = normalize_match_key(vtitle), normalize_match_key(owner)
            has_prod = bool((p_key and len(p_key) >= 2 and (p_key[:2] in vt_key or p_key[:2] in owner_key)) or (norm_prod and len(norm_prod) >= 2 and norm_prod[:2] in norm_vtitle))
            if not (has_prod or "official" in v_low or "mv" in v_low):
                continue
            if len(norm_title) <= 3 and norm_prod and norm_prod not in norm_vtitle and not (p_key and p_key in owner_key):
                continue
            return vid
    except Exception:
        pass
    return ""


def crawl_youtube_multilingual_zero_quota() -> list:
    queries = [
        "初音ミク Official MV -歌ってみた -cover -shorts", "重音テト Official MV -歌ってみた -cover -shorts",
        "重音テトSV Official MV -歌ってみた -cover -shorts", "可不 Official MV -歌ってみた -cover -shorts",
        "足立レイ Official MV -cover -shorts", "카사네 테토 MV -cover -커버 -shorts",
        "하츠네 미쿠 MV -cover -커버 -shorts", "보컬로이드 오리지널 MV -cover -커버",
        "Kasane Teto Original MV -cover -shorts", "Hatsune Miku Original Song MV -cover -shorts",
        "VOCALOID Original MV 2026 -cover -shorts",
    ]
    yt_ids, headers = [], {"User-Agent": CHROME_UA}
    for q in queries:
        try:
            res = requests.get("https://www.youtube.com/results", params={"search_query": q}, headers=headers, timeout=10)
            if res.status_code == 200:
                for vid in re.findall(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', res.text)[:15]:
                    if vid not in yt_ids:
                        yt_ids.append(vid)
        except Exception:
            pass
    print(f"YouTube 日韓英マルチリンガル探索: {len(yt_ids)} 件取得")
    return yt_ids


def get_niconico_thumbinfo(nc_id: str) -> dict:
    if not nc_id:
        return {}
    try:
        res = requests.get(f"https://ext.nicovideo.jp/api/getthumbinfo/{nc_id}", headers={"User-Agent": USER_AGENT}, timeout=10)
        root = ET.fromstring(res.text)
        if root.attrib.get("status") == "ok":
            thumb = root.find("thumb")
            tags = " ".join(t.text for t in thumb.findall("tags/tag") if t.text)
            parts = thumb.findtext("length", "3:00").split(":")
            dur_sec = int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 180
            return {
                "nc_id": nc_id, "title": thumb.findtext("title", ""), "description": thumb.findtext("description", ""),
                "tags": tags, "producer": thumb.findtext("user_nickname", ""),
                "published_at": thumb.findtext("first_retrieve", ""), "duration_sec": dur_sec,
            }
    except Exception:
        pass
    return {}


def verify_and_purge_existing_pool(youtube, raw_items: list) -> list:
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

    verified = []
    for item in raw_items:
        yid, nid, title = (item.get("youtube_id") or "").strip(), (item.get("niconico_id") or "").strip(), item.get("title", "")
        nc_title_str, nc_meta_str, nc_pub_str = "", "", ""
        if nid and (nc_info := get_niconico_thumbinfo(nid)):
            if not is_valid_vocaloid_mv(nc_info["title"], nc_info["description"], nc_info["tags"], nc_info["duration_sec"], is_niconico=True, producer=nc_info.get("producer") or item.get("producer", "")):
                continue
            nc_title_str, nc_meta_str, nc_pub_str = nc_info["title"], f"{nc_info['tags']} {nc_info['description'][:300]}", nc_info.get("published_at", "")

        yt_title_str, yt_meta_str, yt_pub_str = "", "", ""
        if yid and yid in yt_meta:
            snippet = yt_meta[yid].get("snippet", {})
            dur_sec = parse_iso_duration_seconds(yt_meta[yid].get("contentDetails", {}).get("duration", ""))
            y_title, y_desc, y_tags, y_channel = snippet.get("title", ""), snippet.get("description", ""), " ".join(snippet.get("tags", [])), snippet.get("channelTitle", "")
            yt_pub_str = snippet.get("publishedAt", "")
            if not is_valid_vocaloid_mv(y_title, y_desc, y_tags, dur_sec, is_niconico=False, yt_category_id=snippet.get("categoryId", "10"), producer=y_channel or item.get("producer", ""), has_niconico=bool(nid)):
                continue
            yt_title_str, yt_meta_str = y_title, f"{y_tags} {y_desc[:300]}"
            if nid and title:
                norm_t, norm_yt = normalize_compare_str(title), normalize_compare_str(y_title)
                if len(norm_t) >= 2 and norm_t not in norm_yt and norm_yt not in norm_t:
                    vdb = lookup_vocadb_by_pv("NicoNicoDouga", nid)
                    if vdb.get("rejected") or vdb.get("youtube_id") != yid:
                        item["youtube_id"] = ""

        combined_titles, combined_metas = f"{yt_title_str} {nc_title_str}".strip(), f"{yt_meta_str} {nc_meta_str}".strip()
        if combined_titles or combined_metas:
            item["vocal"] = detect_vocals(combined_titles, combined_metas, item.get("vocal", ""))
        pub_candidates = [s for s in (item.get("published_at", ""), item.get("yt_published_at", ""), item.get("nc_published_at", ""), yt_pub_str, nc_pub_str) if s and str(s).strip()]
        if pub_candidates:
            item["published_at"] = min(pub_candidates)
        if is_eligible_ranking_song(item, canonical_map):
            verified.append(item)
    return verified


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

    pool, by_yt, by_nc, by_tp = [], {}, {}, {}

    def upsert_song(entry: dict):
        yid, nid = (entry.get("youtube_id") or "").strip(), (entry.get("niconico_id") or "").strip()
        title = clean_song_title(entry.get("title", ""), entry.get("producer", ""))
        producer, vocal = (entry.get("producer") or "ボカロP").strip(), entry.get("vocal") or "VOCALOID"
        pub_at = (entry.get("published_at") or entry.get("yt_published_at") or entry.get("nc_published_at") or "").strip()
        if not yid and not nid:
            return
        tp_key = f"{normalize_compare_str(title)}::{normalize_compare_str(producer)}" if title else ""
        target = by_nc.get(nid) if (nid and nid in by_nc) else (by_yt.get(yid) if (yid and yid in by_yt) else by_tp.get(tp_key))
        if target is not None:
            if yid and not target.get("youtube_id") and yid not in by_yt: target["youtube_id"] = yid; by_yt[yid] = target
            if nid and not target.get("niconico_id") and nid not in by_nc: target["niconico_id"] = nid; by_nc[nid] = target
            if title and (not target.get("title") or target["title"] == target.get("producer")): target["title"] = title
            if producer and producer != "ボカロP" and target.get("producer") == "ボカロP": target["producer"] = producer
            if vocal and vocal != "VOCALOID" and (target.get("vocal") in ["", "VOCALOID", "VOCALOID / 合成音声"] or any(d in vocal for d in DERIVATIVE_CHARACTERS)):
                target["vocal"] = vocal
            if pub_at: target["published_at"] = min(target.get("published_at", ""), pub_at) if target.get("published_at") else pub_at
            return
        yid = "" if yid in by_yt else yid
        nid = "" if nid in by_nc else nid
        if not yid and not nid:
            return
        new_item = {"song_id": entry.get("song_id") or f"song_{nid or yid}", "title": title or "Unknown", "producer": producer, "vocal": vocal, "youtube_id": yid, "niconico_id": nid, "published_at": pub_at}
        pool.append(new_item)
        if yid: by_yt[yid] = new_item
        if nid: by_nc[nid] = new_item
        if tp_key: by_tp[tp_key] = new_item

    for item in verify_and_purge_existing_pool(youtube, raw_loaded):
        upsert_song(item)

    canonical_map = build_canonical_originals_map(pool)
    for v_item in crawl_vocadb_global_and_domestic():
        if is_eligible_ranking_song(v_item, canonical_map):
            upsert_song(v_item)

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
            upsert_song(cand)

    canonical_map = build_canonical_originals_map(pool)
    new_yt_ids = [vid for vid in crawl_youtube_multilingual_zero_quota() if vid not in by_yt]
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
                    upsert_song(cand)
        except Exception as e:
            print(f"YouTube multilingual batch check error: {e}")

    repaired_count = 0
    for song in pool:
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
