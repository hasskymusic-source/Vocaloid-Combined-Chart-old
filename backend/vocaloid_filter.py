import re

VOCAL_SYNONYMS = {
    "初音ミク": ["初音ミク", "하츠네 미쿠", "hatsune miku", "miku"], "重音テト": ["重音テト", "重音テトsv", "카사네 테토", "kasane teto", "teto"],
    "亞北ネル": ["亞北ネル", "亜北ネル", "akita neru", "아키타 네루"], "弱音ハク": ["弱音ハク", "yowane haku", "요와네 하쿠"],
    "鏡音リン": ["鏡音リン", "카가미네 린", "kagamine rin"], "鏡音レン": ["鏡音レン", "카가미네 렌", "kagamine len"],
    "巡音ルカ": ["巡音ルカ", "메구리네 루카", "megurine luka"], "MEIKO": ["meiko", "메이코", "メイコ"],
    "KAITO": ["kaito", "카이토", "カイト"], "足立レイ": ["足立レイ", "아다치 레이", "adachi rei"],
    "ナースロボ＿タイプＴ": ["ナースロボ＿タイプｔ", "ナースロボ_タイプt", "ナースロボ", "nursehoro"],
    "唄音ウタ(デフォ子)": ["唄音ウタ", "デフォ子", "utane uta", "defoko"], "桃音モモ": ["桃音モモ", "momone momo"],
    "重音テッド": ["重音テッド", "kasane ted"], "欲音ルコ": ["欲音ルコ", "yokune ruko"], "波音リツ": ["波音リツ", "namine ritsu"],
    "健音テイ": ["健音テイ", "sukone tei"], "雪歌ユフ": ["雪歌ユフ", "sekka yufu"], "春歌ナナ": ["春歌ナナ", "haruka nana"],
    "闇音レンリ": ["闇音レンリ", "yamine renri"], "ゲキヤク": ["ゲキヤク", "gekiyaku"], "カゼヒキ": ["カゼヒキ", "kazehiki"],
    "咲音メイコ": ["咲音メイコ", "sakine meiko"], "骸音シーエ": ["骸音シーエ", "calne ca"], "雑音ミク": ["雑音ミク", "zatsune miku"],
    "鋼音ミク": ["鋼音ミク", "hagane miku"], "アカイト": ["アカイト", "akaito"], "GUMI": ["gumi", "구미", "megpoid", "メグッポイド"],
    "v_flower": ["v_flower", "flower", "플라워", "ci flower"], "IA": ["ia", "이아"], "歌愛ユキ": ["歌愛ユキ", "카아이 유키", "kaai yuki"],
    "音街ウナ": ["音街ウナ", "오토마치 우나", "otomachi una"], "可不": ["可不", "kafu", "카후"], "星界": ["星界", "sekai", "세카이"],
    "裏命": ["裏命", "rime", "리메"], "狐子": ["狐子", "coko", "코코"], "羽累": ["羽累", "haru"],
    "知声": ["知声", "chis-a", "치세이"], "ずんだもん": ["ずんだもん", "준단몬", "zundamon"], "結月ゆかり": ["結月ゆかり", "유즈키 유카리", "yuzuki yukari"],
    "紲星あかり": ["紲星あかり", "키즈나 아카리", "kizuna akari"], "琴葉姉妹": ["琴葉姉妹", "琴葉茜", "琴葉葵", "kotonoha"],
    "小春六花": ["小春六花", "koharu rikka"], "夏色花梨": ["夏色花梨", "natsuiro karin"], "花隈千冬": ["花隈千冬", "hanakuma chifuyu"],
    "宮舞モカ": ["宮舞モカ", "miyamai moka"], "弦巻マキ": ["弦巻マキ", "tsurumaki maki"], "さとうささら": ["さとうささら", "satou sasara"],
    "すずきつづみ": ["すずきつづみ", "suzuki tsudumi"], "双葉湊音": ["双葉湊音", "futaba minato"], "東北きりたん": ["東北きりたん", "tohoku kiritan"],
    "東北ずん子": ["東北ずん子", "tohoku zunko"], "東北イタコ": ["東北イタコ", "tohoku itako"], "神威がくぽ": ["神威がくぽ", "がくっぽいど", "kamui gakupo"],
    "氷山キヨテル": ["氷山キヨテル", "hiyama kiyoteru"], "猫村いろは": ["猫村いろは", "nekomura iroha"], "miki": ["開発コードmiki", "sf-a2 miki"],
    "MAYU": ["mayu"], "四国めたん": ["四国めたん", "shikoku metan"], "春日部つむぎ": ["春日部つむぎ", "kasukabe tsumugi"],
    "冥鳴ひまり": ["冥鳴ひまり", "meimei himari"], "京町セイカ": ["京町セイカ", "kyomachi seika"], "ついなちゃん": ["ついなちゃん", "tsuina-chan"],
    "桜乃そら": ["桜乃そら", "haruno sora"], "フリモメン": ["フリモメン", "frimomen"], "洛天依": ["洛天依", "luo tianyi"],
    "心華": ["心華", "xin hua"], "SeeU": ["seeu", "시유"], "UNI": ["uni", "유니"],
}

NON_VOCALOID_GENRE_VOCALS = {
    "yi xi", "이시", "奕夕", "solaria", "eleanor forte", "エレノア・フォルテ",
    "kevin", "natalie", "ninezero", "asterian", "saros", "anri", "jun", "hayden",
    "qing su", "mo chen", "an xiao", "feng yi", "cong zheng", "xuan yu", "cheng xiao", "weina",
}

DERIVATIVE_CHARACTERS = {"亞北ネル", "弱音ハク", "咲音メイコ", "雑音ミク", "鋼音ミク", "アカイト"}

NG_KEYWORDS = [
    "歌ってみた", "踊ってみた", "演奏してみた", "叩いてみた", "弾いてみた", "切り抜き", "まとめ", "メドレー", "カラオケ", "off vocal", "instrumental",
    "reaction", "リアクション", "プロセカ", "プロジェクトセカイ", "譜面", "耐久", "1時間", "1 hour", "作業用", "解説", "ランキング", "比較", "mmd",
    "mikumikudance", "yyb", "tda", "モデル", "モーション配布", "カメラモーション", "mmdモーション", "マイクラ", "マインクラフト", "minecraft", "再現", "レッドストーン", "音ブロック", "同時視聴",
    "初見", "配信", "live", "ライブ", "チャンネル登録", "万人ありがとう", "#shorts", "shorts", "ショート", "tiktok", "違い", "感性プレイ", "ホロドリ",
    "藤井風", "cover", "covered by", "커버", "불러보았다", "piano tutorial", "sheet music", "旅行", "車載", "散歩", "ツーリング", "ドライブ", "鉄道",
    "夜景", "ゲートブリッジ", "行ってみた", "行ってみない", "食べてみた", "作ってみた", "描いてみた", "買ってみた", "ソフトウェアトーク", "voiceroid",
    "voicepeak", "a.i.voice", "ボイロ", "ゆっくり", "実況", "プレイ動画", "ゲーム実況", "料理", "キッチン", "劇場", "茶番", "ラジオ", "雑談",
    "重音テトが行く", "講座", "検証", "紹介", "レビュー", "ニュース", "カバー", "ｶﾊﾞｰ", "セルフカバー", "self cover", "替え歌", "パロディ", "parody",
    "개사", "패러디", "재수머라이저", "팬메이드", "한글자막", "자막", "번역", "매쉬업", "알아보자", "非公式mv", "非公式pv", "ファンメイド", "ファンアニメ",
    "二次創作", "2次創作", "fanmade", "fan made", "fan animation", "fan mv", "fan video", "fan animated", "animatic", "転載", "無断転載",
    "中文字幕", "韓国語字幕", "字幕", "subbed", "eng sub", "kor sub", "translated", "reupload", "reprint", "archival", "nightcore", "mashup",
    "マッシュアップ", "walkthrough", "tutorial", "チュートリアル", "デモンストレーション", "demonstration", "デモソング", "ボイスタイプ紹介",
    "why vocaloid", "ai music video", "ai-generated", "ai generated", "tribute", "pear teto", "toxic gossip train", "butcher vanity",
]

NG_PRODUCER_KEYWORDS = [
    "archive", "archival", "reupload", "reprint", "nightcore", "subbed", "translated", "parody",
    "ai-generated", "ai generated", "teto kasane-chan", "alice clipton", "pika1978100", "harrymacdowel",
    "horror skunx", "turbo lines music", "vane lily",
]

REQUIRED_MUSIC_INDICATORS = [
    "vocaloid", "ボカロ", "보컬로이드", "ボカロオリジナル曲", "オリジナル曲", "synthesizerv", "synthesizer_v", "synthesizer v",
    "synthv", "synthesizervオリジナル曲", "utauオリジナル曲", "cevioオリジナル曲", "voicevoxオリジナル曲", "ミクオリジナル曲",
    "テトオリジナル曲", "重音テトsv", "可不オリジナル曲", "gumiオリジナル曲", "リンオリジナル曲", "レンオリジナル曲",
    "ルカオリジナル曲", "flowerオリジナル曲", "ユキオリジナル曲", "レイオリジナル曲", "ウナオリジナル曲", "ゆかりオリジナル曲",
    "vocarock", "ボカコレ", "vocacolle", "vocaloid新曲リンク", "vocaloid殿堂入り", "vocaloid伝説入り", "music video", "official mv", "【mv】", "[mv]",
]

META_BRACKET_RE = re.compile(
    r"^(?:初音ミク|重音テト|重音テトSV|亞北ネル|亜北ネル|弱音ハク|GUMI|可不|鏡音リン|鏡音レン|巡音ルカ|flower|v_flower|IA|歌愛ユキ|ずんだもん|足立レイ|宮舞モカ|"
    r"카사네\s*테토|하츠네\s*미쿠|보컬로이드|Kasane\s*Teto|Hatsune\s*Miku|VOCALOID|ボカロ|Synthesizer\s*V|SynthV|"
    r"オリジナル|オリジナル曲|オリジナル曲PV|PV|MV|Official|Music\s*Video|公式|新曲)+$", re.IGNORECASE,
)

YT_ID_PATTERN = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})")
NC_ID_PATTERN = re.compile(r"(sm\d{7,9})")
ISO_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")

KNOWN_CANONICAL_ORIGINALS = {
    "igaku": "原口沙輔", "イガク": "原口沙輔", "mesmerizer": "サツキ", "メズマライザー": "サツキ",
    "메소머라이저": "サツキ", "재수머라이저": "サツキ", "yararara": "abm", "ヤラララ": "abm",
    "birdbrain": "ジェイミー", "トリアタマ": "ジェイミー", "혼돈부기": "jonyakitory", "混沌ブギ": "jonyakitory",
    "천본앵": "黒うさ", "千本桜": "黒うさ", "토리노코시티": "40mp", "トリノコシティ": "40mp", "oddsends": "ryo",
    "미스터리": "mimi", "ミステリー": "mimi", "루프더룸": "ルシノ", "ループザルーム": "ルシノ",
    "loopingtherooms": "ルシノ", "ブレインロット": "東京真中",
}

HUMAN_ARTIST_TYPES = {"OtherVocalist", "Utaite", "OtherIndividual", "OtherGroup"}
SYNTH_ARTIST_TYPES = {"Vocaloid", "UTAU", "SynthesizerV", "CeVIO", "VOICEVOX", "Neutrino", "VoiSona", "OtherVoiceSynthesizer"}


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
        if re.match(r"^[a-z0-9\s\-]+$", kw_low) and (len(kw_low) <= 4 or kw_low in NON_VOCALOID_GENRE_VOCALS):
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


def is_valid_vocaloid_mv(
    title: str, description: str = "", tags: str = "", duration_sec: int = 180,
    is_niconico: bool = False, yt_category_id: str = "10", producer: str = "", has_niconico: bool = False,
) -> bool:
    if duration_sec < 90 or duration_sec > 420:
        return False
    t_low, d_low, tags_low, p_low = (title or "").lower(), (description or "").lower(), (tags or "").lower(), (producer or "").lower()
    if any(ng in t_low or ng in tags_low for ng in NG_KEYWORDS) or (p_low and any(ng_p in p_low for ng_p in NG_PRODUCER_KEYWORDS)):
        return False
    if "#shorts" in d_low or "mikumikudance" in d_low or "yyb式" in d_low or "tda式" in d_low:
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
    if any(ng in t_low for ng in NG_KEYWORDS) or (p_low and any(ng_p in p_low for ng_p in NG_PRODUCER_KEYWORDS)):
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
