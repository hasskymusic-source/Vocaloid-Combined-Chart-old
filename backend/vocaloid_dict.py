import re

VOCAL_SYNONYMS = {
    "初音ミク": ["初音ミク", "하츠네 미쿠", "hatsune miku", "miku"],
    "重音テト": ["重音テト", "重音テトsv", "카사네 테토", "kasane teto", "teto"],
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
    "知声": ["知声", "chis-a", "치세이"], "ずんだもん": ["ずんだもん", "준단몬", "zundamon"],
    "結月ゆかり": ["結月ゆかり", "유즈키 유카리", "yuzuki yukari"], "紲星あかり": ["紲星あかり", "키즈나 아카리", "kizuna akari"],
    "琴葉姉妹": ["琴葉姉妹", "琴葉茜", "琴葉葵", "kotonoha"], "小春六花": ["小春六花", "koharu rikka"],
    "夏色花梨": ["夏色花梨", "natsuiro karin"], "花隈千冬": ["花隈千冬", "hanakuma chifuyu"],
    "宮舞モカ": ["宮舞モカ", "miyamai moka"], "弦巻マキ": ["弦巻マキ", "tsurumaki maki"], "さとうささら": ["さとうささら", "satou sasara"],
    "すずきつづみ": ["すずきつづみ", "suzuki tsudumi"], "双葉湊音": ["双葉湊音", "futaba minato"],
    "東北きりたん": ["東北きりたん", "tohoku kiritan"], "東北ずん子": ["東北ずん子", "tohoku zunko"], "東北イタコ": ["東北イタコ", "tohoku itako"],
    "神威がくぽ": ["神威がくぽ", "がくっぽいど", "kamui gakupo"], "氷山キヨテル": ["氷山キヨテル", "hiyama kiyoteru"],
    "猫村いろは": ["猫村いろは", "nekomura iroha"], "miki": ["開発コードmiki", "sf-a2 miki"], "MAYU": ["mayu"],
    "四国めたん": ["四国めたん", "shikoku metan"], "春日部つむぎ": ["春日部つむぎ", "kasukabe tsumugi"],
    "冥鳴ひまり": ["冥鳴ひまり", "meimei himari"], "京町セイカ": ["京町セイカ", "kyomachi seika"], "ついなちゃん": ["ついなちゃん", "tsuina-chan"],
    "桜乃そら": ["桜乃そら", "haruno sora"], "フリモメン": ["フリモメン", "frimomen"], "洛天依": ["洛天依", "luo tianyi"],
    "心華": ["心華", "xin hua"], "SeeU": ["seeu", "시유"], "UNI": ["uni", "유니"],
    "雨衣": ["雨衣", "voisona 雨衣", "voisona雨衣"],
    "鳴花ヒメ": ["鳴花ヒメ", "meika hime"], "鳴花ミコト": ["鳴花ミコト", "meika mikoto"],
    "OИE": ["oиe", "aria on the planetes one", "cevio one"],
    "VY1": ["vy1", "mizki"], "VY2": ["vy2", "yuma"], "#kzn": ["#kzn", "キズナちゃん", "kznちゃん"],
    "夢ノ結唱 POPY": ["夢ノ結唱", "夢ノ結唱 popy"], "夢ノ結唱 ROSE": ["夢ノ結唱 rose"],
    "無來": ["無來", "voisona 無來"], "那由歌": ["那由歌", "voisona 那由歌"],
    "梵そよぎ": ["梵そよぎ", "soyogi"], "紡乃世詞音": ["紡乃世詞音", "tsunose kotone"],
    "櫻歌ミコ": ["櫻歌ミコ", "ouka miko"], "つくよみちゃん": ["つくよみちゃん", "tsukuyomi-chan"],
    "めろう": ["めろう", "neutrino めろう"], "No.7": ["no.7", "neutrino no.7"],
    "ギャラ子": ["ギャラ子", "galaco"], "fuiro": ["fuiro", "フイロ"],
    "機流音": ["機流音", "kiryune"], "AiSuu": ["aisuu"],
}

NON_VOCALOID_GENRE_VOCALS = {
    "yi xi", "이시", "奕夕", "solaria", "eleanor forte", "エレノア・フォルテ",
    "kevin", "natalie", "ninezero", "asterian", "saros", "anri", "jun", "hayden",
    "qing su", "mo chen", "an xiao", "feng yi", "cong zheng", "xuan yu", "cheng xiao", "weina",
}

DERIVATIVE_CHARACTERS = {"亞北ネル", "弱音ハク", "咲音メイコ", "雑音ミク", "鋼音ミク", "アカイト"}

STRICT_NG_KEYWORDS = [
    "歌ってみた", "踊ってみた", "演奏してみた", "叩いてみた", "弾いてみた", "切り抜き", "メドレー", "off vocal", "instrumental",
    "リアクション", "耐久", "1時間", "1 hour", "作業用", "mikumikudance", "yyb式", "tda式", "マイクラ", "マインクラフト", "minecraft",
    "レッドストーン", "音ブロック", "同時視聴", "初見", "チャンネル登録", "万人ありがとう", "#shorts", "piano tutorial", "sheet music",
    "covered by", "커버", "불러보았다", "ソフトウェアトーク", "voiceroid", "voicepeak", "a.i.voice", "ボイロ", "ゆっくり",
    "ゲーム実況", "プレイ動画", "重音テトが行く", "セルフカバー", "self cover", "替え歌", "개사", "패러디", "재수머라이저",
    "팬메이드", "한글자막", "中文字幕", "韓国語字幕", "非公式mv", "非公式pv", "ファンメイド", "ファンアニメ", "二次創作", "2次創作",
    "fanmade", "fan made", "fan animation", "fan mv", "fan video", "fan animated", "animatic", "無断転載", "reupload", "reprint",
    "マッシュアップ", "デモンストレーション", "ボイスタイプ紹介", "why vocaloid", "ai music video", "ai-generated", "ai generated",
    "pear teto", "toxic gossip train", "butcher vanity", "モーション配布", "カメラモーション", "mmdモーション", "譜面", "譜面確認",
    "音ゲー譜面", "プロセカ譜面", "プロセカプレイ", "3dmv", "2dmv", "セカイver", "all perfect", "full combo", "感性プレイ",
    "ホロドリ", "藤井風", "行ってみた", "行ってみない", "食べてみた", "作ってみた", "描いてみた", "買ってみた",
]

TITLE_ONLY_NG_KEYWORDS = [
    "カラオケ", "ランキング", "まとめ", "解説", "比較", "再現", "配信", "ライブ", "ショート", "違い", "モデル",
    "旅行", "車載", "散歩", "ツーリング", "ドライブ", "鉄道", "夜景", "ゲートブリッジ", "実況", "料理", "キッチン",
    "劇場", "茶番", "ラジオ", "雑談", "講座", "検証", "紹介", "レビュー", "ニュース", "カバー", "ｶﾊﾞｰ", "パロディ",
    "자막", "번역", "매쉬업", "알아보자", "転載", "字幕", "チュートリアル", "デモソング",
]

WORD_BOUNDARY_NG_KEYWORDS = [
    "live", "cover", "shorts", "tiktok", "mmd", "yyb", "tda", "reaction", "parody",
    "subbed", "eng sub", "kor sub", "translated", "archival", "nightcore", "mashup",
    "walkthrough", "tutorial", "demonstration", "tribute",
]

STRICT_WORD_BOUNDARY_NG_KEYWORDS = [
    "mmd", "nightcore", "mashup", "parody", "reaction", "walkthrough",
    "demonstration", "archival", "subbed", "eng sub", "kor sub", "translated",
]

NG_KEYWORDS = STRICT_NG_KEYWORDS + TITLE_ONLY_NG_KEYWORDS + WORD_BOUNDARY_NG_KEYWORDS

NG_PRODUCER_KEYWORDS = [
    "archive", "archival", "reupload", "reprint", "nightcore", "subbed", "translated", "parody",
    "ai-generated", "ai generated", "teto kasane-chan", "alice clipton", "pika1978100", "harrymacdowel",
    "horror skunx", "turbo lines music", "vane lily",
]

NICONICO_ORIGINAL_TAGS = [
    "ボカロオリジナル曲", "vocaloidオリジナル曲", "ミクオリジナル曲", "テトオリジナル曲", "リンオリジナル曲",
    "レンオリジナル曲", "ルカオリジナル曲", "gumiオリジナル曲", "iaオリジナル曲", "可不オリジナル曲",
    "flowerオリジナル曲", "ユキオリジナル曲", "レイオリジナル曲", "ウナオリジナル曲", "ゆかりオリジナル曲",
    "synthesizervオリジナル曲", "utauオリジナル曲", "cevioオリジナル曲", "voicevoxオリジナル曲",
    "vocaloid殿堂入り", "vocaloid伝説入り", "vocaloid神話入り",
]

NICONICO_STRICT_NON_ORIGINAL_TAGS = [
    "歌ってみた", "踊ってみた", "演奏してみた", "叩いてみた", "弾いてみた", "mikumikudance",
    "譜面", "3dmv", "2dmv", "セカイver", "ゆっくり", "ソフトウェアトーク", "ゲーム実況",
    "off vocal", "メドレー", "作業用", "耐久", "切り抜き",
]

REQUIRED_MUSIC_INDICATORS = list(dict.fromkeys(NICONICO_ORIGINAL_TAGS + [
    "vocaloid", "ボカロ", "보컬로이드", "オリジナル曲", "synthesizerv", "synthesizer_v", "synthesizer v",
    "synthv", "重音テトsv", "vocarock", "ボカコレ", "vocacolle", "vocaloid新曲リンク", "music video", "official mv", "【mv】", "[mv]",
]))

META_BRACKET_RE = re.compile(
    r"^(?:初音ミク|重音テト|重音テトSV|亞北ネル|亜北ネル|弱音ハク|GUMI|可不|鏡音リン|鏡音レン|巡音ルカ|flower|v_flower|IA|歌愛ユキ|ずんだもん|足立レイ|宮舞モカ|雨衣|"
    r"카사네\s*테토|하츠네\s*미쿠|보컬로이드|Kasane\s*Teto|Hatsune\s*Miku|VOCALOID|ボカロ|Synthesizer\s*V|SynthV|"
    r"オリジナル|オリジナル曲|オリジナル曲PV|PV|MV|Official|Music\s*Video|公式|新曲)+$", re.IGNORECASE,
)

YT_ID_PATTERN = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})")
NC_ID_PATTERN = re.compile(r"\b((?:sm|so)\d{7,9})\b")
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
