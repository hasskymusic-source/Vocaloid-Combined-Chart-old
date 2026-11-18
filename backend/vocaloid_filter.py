import re
from vocaloid_dict import (
    DERIVATIVE_CHARACTERS, HUMAN_ARTIST_TYPES, ISO_DURATION_RE, KNOWN_CANONICAL_ORIGINALS,
    META_BRACKET_RE, NC_ID_PATTERN, NG_KEYWORDS, NG_PRODUCER_KEYWORDS, NICONICO_ORIGINAL_TAGS,
    NICONICO_STRICT_NON_ORIGINAL_TAGS, NON_VOCALOID_GENRE_VOCALS, REQUIRED_MUSIC_INDICATORS,
    STRICT_NG_KEYWORDS, STRICT_WORD_BOUNDARY_NG_KEYWORDS, SYNTH_ARTIST_TYPES,
    TITLE_ONLY_NG_KEYWORDS, VOCAL_SYNONYMS, WORD_BOUNDARY_NG_KEYWORDS, YT_ID_PATTERN,
)


def parse_iso_duration_seconds(duration_str: str) -> int:
    m = ISO_DURATION_RE.match(duration_str or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else 0


def normalize_compare_str(s: str) -> str:
    return re.sub(r"[\s\*\-\_・／/!！?？'\"「」『』【】\[\]()（）pPチャンネルchannelofficialmvpv]", "", (s or "").lower())


def normalize_match_key(s: str) -> str:
    """本家曲・ボカロP照合用に文字を欠損させず記号・空白のみを除去する"""
    return re.sub(r"[\W_]+", "", (s or "").lower())


VOCAL_NORM_SET = {normalize_match_key(v) for k, syns in VOCAL_SYNONYMS.items() for v in ([k] + syns) if normalize_match_key(v)}


def _find_keywords_with_pos(text_low: str, keywords: list) -> list:
    found = []
    for kw in keywords:
        kw_low = kw.lower()
        if re.match(r"^[a-z0-9\s\-\.]+$", kw_low) and (len(kw_low) <= 4 or kw_low in NON_VOCALOID_GENRE_VOCALS):
            m = re.search(rf"\b{re.escape(kw_low)}\b", text_low)
            pos = m.start() if m else -1
        else:
            pos = text_low.find(kw_low)
        if pos != -1:
            found.append((pos, kw))
    return found


def detect_vocals_list(text: str) -> list:
    """テキスト内で登場した位置順（出現順）に対象ボーカル・キャラクター名を抽出する"""
    if not text:
        return []
    text_low = text.lower()
    found = [(min(p for p, _ in hits), canonical) for canonical, syns in VOCAL_SYNONYMS.items() if (hits := _find_keywords_with_pos(text_low, syns))]
    found.sort(key=lambda x: x[0])
    return [c for _, c in found]


def detect_non_vocaloid_vocals_list(text: str) -> list:
    """海外リアル系汎用音源（Yi Xi, Solaria等）がテキストに含まれる場合に位置順で返す"""
    if not text:
        return []
    hits = sorted(_find_keywords_with_pos(text.lower(), sorted(NON_VOCALOID_GENRE_VOCALS)), key=lambda x: x[0])
    return [kw for _, kw in hits]


def _first_vocal_positions(text_low: str) -> tuple:
    tar = [pos for syns in VOCAL_SYNONYMS.values() for pos, _ in _find_keywords_with_pos(text_low, syns)]
    non = [pos for pos, _ in _find_keywords_with_pos(text_low, list(NON_VOCALOID_GENRE_VOCALS))]
    return (min(tar) if tar else None), (min(non) if non else None)


def detect_vocals(title_text: str, meta_text: str = "", fallback_text: str = "") -> str:
    """3段階優先ボーカル判定システム"""
    title_vocals, meta_vocals, fallback_vocals = detect_vocals_list(title_text), detect_vocals_list(meta_text), detect_vocals_list(fallback_text)
    if title_vocals:
        result = list(title_vocals) + [c for c in meta_vocals if c in DERIVATIVE_CHARACTERS and c not in title_vocals]
    elif meta_vocals:
        result = list(meta_vocals)
    else:
        result = list(fallback_vocals)
    if "亞北ネル" in result and "鏡音リン" in result and "鏡音リン" not in title_vocals:
        result.remove("鏡音リン")
    return "・".join(result[:4]) if result else "VOCALOID"


def clean_song_title(raw_title: str, producer: str = "") -> str:
    t = re.sub(r"【[^】]*】|\[[^\]]*\]", " ", (raw_title or "").strip()).strip()
    m_single = re.search(r"(?<![A-Za-z])'([^']{2,40})'(?![A-Za-z])\s*(\([^)]{2,40}\))?", t)
    if m_single and not META_BRACKET_RE.match(m_single.group(1).strip()):
        return f"{m_single.group(1).strip()} {m_single.group(2).strip() if m_single.group(2) else ''}".strip()

    t = re.sub(
        r"[『「]([^』」]+)[』」]",
        lambda m: " " if META_BRACKET_RE.match(re.sub(r"[\s・&＆/／]", "", m.group(1).strip())) else f" 「{m.group(1).strip()}」 ", t,
    )
    quoted = re.findall(r"「([^」]+)」", t)
    if len(quoted) == 1 and len(quoted[0]) >= 2 and len(re.sub(r"「[^」]+」", "", t).strip()) <= 12 and not META_BRACKET_RE.match(quoted[0].strip()):
        return quoted[0].strip()

    t = re.sub(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", "", t.replace("「", "").replace("」", ""), flags=re.IGNORECASE)
    t = re.sub(r"\([^)]*(?:MV|Official|Music Video|初音ミク|重音テト|亞北ネル|亜北ネル|弱音ハク|Kasane Teto|Hatsune Miku|카사네 테토|하츠네 미쿠|可不|GUMI|flower|足立レイ|歌愛ユキ)[^)]*\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"#\S+", "", t)
    prod_norm = normalize_compare_str(producer) if producer else ""
    for sep in [" / ", " ／ ", " - ", " ― ", " – "]:
        if sep in t:
            parts = [p.strip() for p in t.split(sep) if p.strip()]
            if len(parts) >= 2:
                filtered = [
                    p for p in parts
                    if not (prod_norm and (normalize_compare_str(p) == prod_norm or normalize_compare_str(p) in prod_norm or prod_norm in normalize_compare_str(p)))
                    and not META_BRACKET_RE.match(re.sub(r"[\s・]", "", p))
                ]
                if filtered:
                    t = filtered[0]
                    break
    t = re.sub(r"^(?:公式|Official\s*MV|MV|PV)\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*(?:オリジナル曲PV|オリジナル曲|オリジナルPV|Official\s*MV|Music\s*Video|MV|PV)$", "", t, flags=re.IGNORECASE)
    return t.strip() or (raw_title or "").strip()


def has_ng_in_title(title_low: str) -> bool:
    """タイトル内のNGワード判定（英単語には単語境界を適用し部分一致誤爆を防ぐ）"""
    t_low = (title_low or "").lower()
    if any(ng in t_low for ng in STRICT_NG_KEYWORDS) or any(ng in t_low for ng in TITLE_ONLY_NG_KEYWORDS):
        return True
    return any(re.search(rf"\b{re.escape(kw)}\b", t_low) for kw in WORD_BOUNDARY_NG_KEYWORDS)


def has_ng_in_tags(tags_low: str, has_niconico_original_tag: bool = False) -> bool:
    """タグ内のNGワード判定（ニコ動本家オリジナルタグがある場合は視聴者タグノイズを許容する）"""
    cleaned_tags = re.sub(r"(?:歌ってみた|踊ってみた|演奏してみた|叩いてみた|弾いてみた)支援", "", (tags_low or "").lower())
    if has_niconico_original_tag:
        return any(ng in cleaned_tags for ng in NICONICO_STRICT_NON_ORIGINAL_TAGS)
    if any(ng in cleaned_tags for ng in STRICT_NG_KEYWORDS):
        return True
    return any(re.search(rf"\b{re.escape(kw)}\b", cleaned_tags) for kw in STRICT_WORD_BOUNDARY_NG_KEYWORDS)


def is_valid_vocaloid_mv(
    title: str, description: str = "", tags: str = "", duration_sec: int = 180,
    is_niconico: bool = False, yt_category_id: str = "10", producer: str = "", has_niconico: bool = False,
) -> bool:
    if duration_sec < 60 or duration_sec > 600:
        return False
    t_low, d_low, tags_low, p_low = (title or "").lower(), (description or "").lower(), (tags or "").lower(), (producer or "").lower()
    if has_ng_in_title(t_low) or (p_low and any(ng_p in p_low for ng_p in NG_PRODUCER_KEYWORDS)):
        return False

    has_nc_orig_tag = is_niconico and any(ind in f"{t_low} {tags_low}" for ind in NICONICO_ORIGINAL_TAGS)
    if has_ng_in_tags(tags_low, has_niconico_original_tag=has_nc_orig_tag):
        return False
    if "#shorts" in d_low or "mikumikudance" in d_low or "yyb式" in d_low or "tda式" in d_low:
        return False
    if not is_niconico and not has_niconico and duration_sec < 90:
        all_txt = f"{t_low} {tags_low} {d_low}"
        if "#shorts" in all_txt or re.search(r"\bshorts\b", all_txt):
            return False
    if is_niconico and not any(ind in f"{t_low} {tags_low}" for ind in REQUIRED_MUSIC_INDICATORS):
        return False
    if not is_niconico and yt_category_id not in ["10", ""] and not any(ind in f"{t_low} {tags_low} {d_low[:200]}" for ind in REQUIRED_MUSIC_INDICATORS):
        return False

    combined_low = f"{title} {tags} {description[:300]}".lower()
    target_vocals = detect_vocals_list(combined_low)
    if is_niconico or has_niconico:
        return len(target_vocals) > 0 or any(k in combined_low for k in ["vocaloid", "ボカロ", "보컬로이드", "synthesizer v", "synthv", "cevio", "utau"])
    if not target_vocals:
        return False
    t_tar_pos, t_non_pos = _first_vocal_positions(t_low)
    if t_non_pos is not None and (t_tar_pos is None or t_non_pos < t_tar_pos):
        return False
    if t_tar_pos is None:
        c_tar_pos, c_non_pos = _first_vocal_positions(combined_low)
        if c_non_pos is not None and (c_tar_pos is None or c_non_pos < c_tar_pos):
            return False
    return True


def extract_vocadb_song_info(data: dict) -> dict:
    if not data or not isinstance(data, dict):
        return {}
    if data.get("songType", "") != "Original":
        return {"rejected": True, "reason": f"songType:{data.get('songType', '')}"}

    yt_id, nc_id, pv_titles, pv_dates = "", "", [], []
    for pv in data.get("pvs", []):
        if pv.get("pvType") == "Original" and not pv.get("disabled", False):
            if pv.get("name"):
                pv_titles.append(pv["name"])
            if pv.get("publishDate"):
                pv_dates.append(str(pv["publishDate"]))
            if pv.get("service") == "Youtube" and not yt_id:
                yt_id = pv.get("pvId", "")
            elif pv.get("service") == "NicoNicoDouga" and not nc_id:
                nc_id = pv.get("pvId", "")

    extracted_producers, main_vocal_artists = [], []
    for art in data.get("artists", []):
        if not isinstance(art, dict):
            continue
        cats, a_info = str(art.get("categories") or ""), art.get("artist") or {}
        a_type, a_name = str(a_info.get("artistType") or ""), str(art.get("name") or a_info.get("name") or "").strip()
        if "Producer" in cats and a_name:
            extracted_producers.append(a_name)
        if "Vocalist" in cats and not art.get("isSupport", False):
            main_vocal_artists.append((a_type, a_name))

    if main_vocal_artists:
        has_human = any(at in HUMAN_ARTIST_TYPES for at, _ in main_vocal_artists)
        has_target_synth = any(detect_vocals_list(an) or (at in SYNTH_ARTIST_TYPES and not detect_non_vocaloid_vocals_list(an)) for at, an in main_vocal_artists)
        if has_human and not has_target_synth:
            return {"rejected": True, "reason": "human_main_vocal"}

    artist_str = data.get("artistString", "")
    producer = artist_str.split(" feat.")[0].strip() if " feat." in artist_str else artist_str
    if (not producer or producer.lower() == "various artists") and extracted_producers:
        producer = ", ".join(dict.fromkeys(extracted_producers))
    vocal_part = artist_str.split(" feat.")[1].strip() if " feat." in artist_str else (
        " ".join(an for _, an in main_vocal_artists if an) if main_vocal_artists else artist_str
    )
    pv_title_str = " ".join(pv_titles)
    if not nc_id:
        c_tar, c_non = _first_vocal_positions(f"{pv_title_str} {vocal_part}".lower())
        if c_tar is None or (c_non is not None and c_non < c_tar):
            return {"rejected": True, "reason": "no_target_vocal_on_yt_only"}

    return {
        "title": data.get("name", ""), "producer": producer,
        "vocal": detect_vocals(pv_title_str, "", vocal_part),
        "youtube_id": yt_id, "niconico_id": nc_id,
        "published_at": data.get("publishDate") or (min(pv_dates) if pv_dates else ""),
    }


def build_canonical_originals_map(songs_list: list) -> dict:
    """ニコ動・YouTube両IDが確定している正当な本家オリジナル曲の照合用マップを構築する"""
    canonical = {}
    for s in songs_list or []:
        if not isinstance(s, dict) or not (s.get("niconico_id") or s.get("nc_id")) or not (s.get("youtube_id") or s.get("yt_id")):
            continue
        cleaned = clean_song_title(str(s.get("title") or ""), str(s.get("producer") or ""))
        t_norm = normalize_match_key(cleaned)
        if len(t_norm) < 3 or t_norm in VOCAL_NORM_SET or META_BRACKET_RE.match(cleaned.strip()):
            continue
        canonical.setdefault(t_norm, []).append(s)
    return canonical


def is_eligible_ranking_song(song_dict: dict, canonical_originals: dict = None) -> bool:
    """収集・集計・ランキング確定の全段階で非ボカロ曲や二次創作動画を除外する共通判定"""
    if not isinstance(song_dict, dict):
        return False
    title, prod, vocal = str(song_dict.get("title") or ""), str(song_dict.get("producer") or ""), str(song_dict.get("vocal") or "")
    nid = str(song_dict.get("niconico_id") or song_dict.get("nc_id") or "").strip()
    t_low, p_low = title.lower(), prod.lower()
    if has_ng_in_title(t_low) or (p_low and any(ng_p in p_low for ng_p in NG_PRODUCER_KEYWORDS)):
        return False
    if nid:
        return True

    v_parts = [v.strip() for v in vocal.split("・") if v.strip()]
    if v_parts and detect_non_vocaloid_vocals_list(v_parts[0]):
        return False
    valid_v = [v for v in v_parts if v.upper() != "VOCALOID" and not detect_non_vocaloid_vocals_list(v)]
    if not valid_v or not (any(v in VOCAL_SYNONYMS for v in valid_v) or detect_vocals_list(f"{title} {vocal}")):
        return False
    t_tar_pos, t_non_pos = _first_vocal_positions(t_low)
    if t_non_pos is not None and (t_tar_pos is None or t_non_pos < t_tar_pos):
        return False

    cand_norms = [normalize_match_key(clean_song_title(title, prod))]
    for rp in re.split(r"[/／\(\)（）\[\]【】]", title):
        rp_clean = clean_song_title(rp, prod)
        rn = normalize_match_key(rp_clean)
        if len(rn) >= 3 and rn not in VOCAL_NORM_SET and not META_BRACKET_RE.match(rp_clean.strip()):
            cand_norms.append(rn)
    token_norms = [
        tn for tok in re.split(r"\s+", title)
        if (tn := normalize_match_key(tok)) and (len(tn) >= 4 or (len(tn) >= 3 and not tn.isascii())) and tn not in VOCAL_NORM_SET
    ]

    p_norm = normalize_match_key(prod)
    for pt in set(cand_norms + token_norms):
        if len(pt) >= 3 and pt not in VOCAL_NORM_SET and pt in KNOWN_CANONICAL_ORIGINALS:
            orig_p = normalize_match_key(KNOWN_CANONICAL_ORIGINALS[pt])
            if not p_norm or (orig_p not in p_norm and p_norm not in orig_p):
                return False
    for pt in set(cand_norms):
        if len(pt) >= 3 and pt not in VOCAL_NORM_SET and canonical_originals and pt in canonical_originals:
            if not any(
                p_norm and normalize_match_key(o.get("producer", ""))
                and (p_norm in normalize_match_key(o.get("producer", "")) or normalize_match_key(o.get("producer", "")) in p_norm)
                for o in canonical_originals[pt]
            ):
                return False
    return True
