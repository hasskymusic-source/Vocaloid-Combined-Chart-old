import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import requests

from vocaloid_dict import (
    NC_ID_PATTERN, NG_PRODUCER_KEYWORDS, NICONICO_ORIGINAL_TAGS, REQUIRED_MUSIC_INDICATORS,
)
from vocaloid_filter import (
    clean_song_title, extract_vocadb_song_info, has_ng_in_tags, has_ng_in_title,
    is_eligible_ranking_song, normalize_compare_str, normalize_match_key,
)

USER_AGENT = "Mozilla/5.0 (compatible; VocaloidCombinedChartBot/9.0)"
CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
SNAP_API_URL = "https://api.search.nicovideo.jp/api/v2/snapshot/video/contents/search"


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
    """新譜・週間トップレート・中長期トレンド・歴代カタログの多軸でVocaDBから収集する"""
    results, seen_pv, now = [], set(), datetime.now(timezone.utc)
    plans = [
        ("https://vocadb.net/api/songs", {"songTypes": "Original", "afterDate": (now - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z"), "sort": "PublishDate", "maxResults": 50}),
        *[("https://vocadb.net/api/songs", {"songTypes": "Original", "afterDate": (now - timedelta(days=d)).strftime("%Y-%m-%dT00:00:00Z"), "sort": "RatingScore", "maxResults": 50}) for d in (14, 45, 120, 365)],
        ("https://vocadb.net/api/songs/top-rated", {"durationHours": 168, "filterBy": "PublishDate", "maxResults": 50}),
        ("https://vocadb.net/api/songs/top-rated", {"durationHours": 720, "maxResults": 50}),
        ("https://vocadb.net/api/songs", {"songTypes": "Original", "sort": "RatingScore", "maxResults": 100}),
        ("https://vocadb.net/api/songs", {"songTypes": "Original", "sort": "FavoritedTimes", "maxResults": 100}),
    ]
    for endpoint, base_params in plans:
        params = {**base_params, "fields": "PVs,Artists", "lang": "Japanese"}
        try:
            res = requests.get(endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=12)
            if res.status_code != 200:
                continue
            payload = res.json()
            items = payload.get("items", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
            for item in items:
                info = extract_vocadb_song_info(item)
                if not info or info.get("rejected"):
                    continue
                yid, nid = info.get("youtube_id", ""), info.get("niconico_id", "")
                key = f"{nid}::{yid}"
                if (yid or nid) and key not in seen_pv and is_eligible_ranking_song(info):
                    seen_pv.add(key)
                    results.append(info)
        except Exception as e:
            print(f"VocaDB fetch warning ({endpoint}): {e}")
    print(f"VocaDB マルチ軸収集（新譜・週間・歴代カタログ）: {len(results)} 件取得")
    return results


def crawl_niconico_comprehensive() -> list:
    """RSS（140件上限）とスナップショットAPI（220件上限）を独立枠で収集し統合する"""
    rss_ids, snap_ids, headers = [], [], {"User-Agent": USER_AGENT}
    rss_urls = [
        "https://www.nicovideo.jp/tag/VOCALOID?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/VOCALOID?sort=f&order=d&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/VOCALOID?sort=m&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%9C%E3%82%AB%E3%83%AD%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%9C%E3%82%AB%E3%83%AD%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=f&order=d&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%9F%E3%82%AF%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/%E3%83%86%E3%83%88%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
        "https://www.nicovideo.jp/tag/SynthesizerV%E3%82%AA%E3%83%AA%E3%82%B8%E3%83%8A%E3%83%AB%E6%9B%B2?sort=h&rss=2.0&lang=ja-jp",
    ]
    for r_url in rss_urls:
        try:
            res = requests.get(r_url, headers=headers, timeout=10)
            if res.status_code == 200:
                for cid in NC_ID_PATTERN.findall(res.text):
                    if cid not in rss_ids:
                        rss_ids.append(cid)
        except Exception:
            pass
    rss_ids = rss_ids[:140]

    now = datetime.now(timezone.utc)
    snap_plans = [
        {"_sort": s, "filters[startTime][gte]": (now - timedelta(days=d)).strftime("%Y-%m-%dT00:00:00+09:00"), "_limit": 50}
        for s, d in [("-mylistCounter", 7), ("-viewCounter", 7), ("-mylistCounter", 14), ("-viewCounter", 35), ("-viewCounter", 120)]
    ] + [{"_sort": "-viewCounter", "_limit": 50}, {"_sort": "-mylistCounter", "_limit": 50}]
    snap_query = "VOCALOID OR ボカロオリジナル曲 OR SynthesizerVオリジナル曲 OR テトオリジナル曲 OR UTAUオリジナル曲 OR CeVIOオリジナル曲 OR VOICEVOXオリジナル曲 OR 重音テトSV"
    for sp in snap_plans:
        params = {"q": snap_query, "targets": "tagsExact", "fields": "contentId", "_context": "VocaloidCombinedChartBot", **sp}
        try:
            res = requests.get(SNAP_API_URL, params=params, headers=headers, timeout=10)
            if res.status_code == 200:
                for item in res.json().get("data", []):
                    if (cid := item.get("contentId")) and cid not in snap_ids:
                        snap_ids.append(cid)
        except Exception:
            pass
    snap_ids = snap_ids[:220]

    merged = list(dict.fromkeys(rss_ids + snap_ids))[:350]
    print(f"ニコニコ動画 独立枠統合収集: RSS {len(rss_ids)} 件 + Snapshot {len(snap_ids)} 件 -> 統合 {len(merged)} 件")
    return merged


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
            if has_ng_in_title(v_low) or any(ng_p in v_low or ng_p in o_low for ng_p in NG_PRODUCER_KEYWORDS):
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


def search_niconico_id_snapshot_strict(target_title: str, target_producer: str, existing_nc_ids: set) -> str:
    """YouTube先行曲のタイトルからニコ動スナップショットAPIで公式ニコ動ID（sm/so）を逆引きする"""
    cleaned_target = clean_song_title(target_title, target_producer)
    target_key = normalize_match_key(cleaned_target)
    if len(target_key) < 2:
        return ""
    params = {
        "q": cleaned_target, "targets": "title",
        "fields": "contentId,title,tags,lengthSeconds,viewCounter",
        "_sort": "-viewCounter", "_limit": 10, "_context": "VocaloidCombinedChartBot",
    }
    try:
        res = requests.get(SNAP_API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
        if res.status_code != 200:
            return ""
        for item in res.json().get("data", []):
            cid = item.get("contentId", "")
            if not cid or cid in existing_nc_ids:
                continue
            dur_sec = int(item.get("lengthSeconds") or 0)
            if dur_sec and (dur_sec < 60 or dur_sec > 600):
                continue
            i_title, i_tags = item.get("title", ""), (item.get("tags") or "").lower()
            if has_ng_in_title(i_title.lower()):
                continue
            has_orig_tag = any(t in i_tags for t in NICONICO_ORIGINAL_TAGS)
            if not (has_orig_tag or any(ind in i_tags for ind in REQUIRED_MUSIC_INDICATORS)):
                continue
            if has_ng_in_tags(i_tags, has_niconico_original_tag=has_orig_tag):
                continue
            item_key = normalize_match_key(clean_song_title(i_title, target_producer))
            if not item_key:
                continue
            if len(target_key) <= 3:
                if item_key != target_key:
                    continue
            elif target_key != item_key and target_key not in item_key and item_key not in target_key:
                continue
            return cid
    except Exception:
        pass
    return ""


def crawl_youtube_multilingual_zero_quota() -> list:
    """日韓英＋多キャラ＋今週新譜フィルタ(sp=EgIIAw==)でYouTubeから収集する"""
    cur_year = datetime.now(timezone.utc).year
    general_queries = [
        "初音ミク Official MV -歌ってみた -cover -shorts", "重音テト Official MV -歌ってみた -cover -shorts",
        "重音テトSV Official MV -歌ってみた -cover -shorts", "音街ウナ Official MV -歌ってみた -cover -shorts",
        "鏡音リン Official MV -歌ってみた -cover -shorts", "鏡音レン Official MV -歌ってみた -cover -shorts",
        "花隈千冬 Official MV -歌ってみた -cover -shorts", "可不 Official MV -歌ってみた -cover -shorts",
        "足立レイ Official MV -cover -shorts", "GUMI Official MV -歌ってみた -cover -shorts",
        "flower ボカロ Official MV -歌ってみた -cover -shorts", "歌愛ユキ Official MV -歌ってみた -cover -shorts",
        "知声 Official MV -歌ってみた -cover -shorts", "宮舞モカ Official MV -歌ってみた -cover -shorts",
        "ずんだもん Official MV -歌ってみた -cover -shorts", "星界 Official MV -歌ってみた -cover -shorts",
        "巡音ルカ Official MV -歌ってみた -cover -shorts", "KAITO Official MV -歌ってみた -cover -shorts",
        "雨衣 VoiSona MV -歌ってみた -cover -shorts",
        "카사네 테토 MV -cover -커버 -shorts", "하츠네 미쿠 MV -cover -커버 -shorts",
        "보컬로이드 오리지널 MV -cover -커버", "Kasane Teto Original MV -cover -shorts",
        "Hatsune Miku Original Song MV -cover -shorts", f"VOCALOID Original MV {cur_year} -cover -shorts",
    ]
    weekly_queries = [
        "初音ミク オリジナル曲 MV -歌ってみた -cover", "重音テト オリジナル曲 MV -歌ってみた -cover",
        "ボカロ オリジナル曲 MV -歌ってみた -cover", "VOCALOID Original Song MV -cover -shorts",
        "보컬로이드 오리지널 곡 MV -cover -커버",
    ]
    yt_ids, headers = [], {"User-Agent": CHROME_UA}
    search_plans = [(q, None, 12) for q in general_queries] + [(q, "EgIIAw==", 15) for q in weekly_queries]
    for q, sp, limit in search_plans:
        params = {"search_query": q, **({"sp": sp} if sp else {})}
        try:
            res = requests.get("https://www.youtube.com/results", params=params, headers=headers, timeout=8)
            if res.status_code == 200:
                for vid in re.findall(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', res.text)[:limit]:
                    if vid not in yt_ids:
                        yt_ids.append(vid)
        except Exception:
            pass
    print(f"YouTube 多キャラ・マルチリンガル・今週新譜探索: {len(yt_ids)} 件取得")
    return yt_ids


def crawl_active_producer_channels_rss(channel_ids: list) -> list:
    """高実績ボカロPのYouTubeチャンネルRSS（0クォータ）から直近14日以内の新作動画IDを収集する"""
    if not channel_ids:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    yt_ids, headers = [], {"User-Agent": USER_AGENT}
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    for cid in channel_ids[:80]:
        if not cid:
            continue
        try:
            res = requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", headers=headers, timeout=6)
            if res.status_code != 200:
                continue
            root = ET.fromstring(res.text)
            for entry in root.findall("atom:entry", ns):
                vid_el, pub_el = entry.find("yt:videoId", ns), entry.find("atom:published", ns)
                if vid_el is None or not vid_el.text:
                    continue
                if pub_el is not None and pub_el.text:
                    try:
                        pub_dt = datetime.fromisoformat(pub_el.text.replace("Z", "+00:00"))
                        if pub_dt < cutoff:
                            continue
                    except Exception:
                        pass
                vid = vid_el.text.strip()
                if vid and vid not in yt_ids:
                    yt_ids.append(vid)
        except Exception:
            pass
    print(f"ボカロPチャンネルRSS巡回（直近14日）: {len(channel_ids[:80])} ch -> {len(yt_ids)} 件取得")
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
