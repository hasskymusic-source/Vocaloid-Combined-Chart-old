/**
 * サイト全体の設定定数および共有ステート管理モジュール
 */

/**
 * 運営者用設定：
 * シェア時に使用する公式公開URL（.pages.dev が外部に出ないよう固定）
 */
export const OFFICIAL_SITE_URL = "https://weekly-vocaloid-combined-chart.com";

/**
 * 任意の感謝メッセージ（「1,000,000 view ありがとうございます！」など）を常時表示したい場合は
 * 下記の SITE_ANNOUNCEMENT_MESSAGE にテキストを入力してください。
 */
export const SITE_ANNOUNCEMENT_MESSAGE = "";
export const COUNTER_NAMESPACE = "vocaloid-combined-chart";
export const COUNTER_KEY = "total-site-views";
export const MILESTONE_THRESHOLDS = [1000000, 500000, 100000, 50000, 10000, 5000, 1000];

export const FAVORITES_STORAGE_KEY = "vcc_favorite_songs_v1";
export const LAST_KNOWN_CHART_STORAGE_KEY = "vcc_latest_chart_cache_v1";
export const ARCHIVE_HISTORY_SESSION_KEY = "vcc_archive_history_session_v1";
export const MOBILE_MEDIA_QUERY = "(max-width: 640px)";

export const WEIGHTS = {
  yt_views: 1,
  yt_likes: 50,
  yt_comments: 100,
  nc_views: 5,
  nc_mylist: 100,
  nc_mylists: 100,
  nc_comments: 10
};

export const METRIC_COLORS = {
  yt_views: "#ef4444",    // 赤: YouTube再生
  yt_likes: "#f97316",    // 橙: YouTube高評価
  yt_comments: "#eab308", // 黄: YouTubeコメント
  nc_views: "#3b82f6",    // 青: ニコ動再生
  nc_mylists: "#06b6d4",  // 水色: ニコ動マイリスト
  nc_comments: "#8b5cf6"  // 紫: ニコ動コメント
};

export const DEFAULT_PAGE_TITLE =
  (typeof document !== "undefined" && document.title) || "週刊VOCALOID™複合ランキング";

export const DEFAULT_META_DESC = (function () {
  if (typeof document === "undefined") return "";
  const el = document.querySelector('meta[name="description"]');
  return el ? el.getAttribute("content") || "" : "";
})();

/**
 * アプリケーション全体で共有するミュータブルな状態オブジェクト
 */
export const state = {
  // チャート・キャッシュ関連
  insightChartInstance: null,
  currentChartData: null,
  archiveHistoryCache: [],
  archiveHistoryLoaded: false,
  cachedArchiveListMeta: [],

  // 通信・動的ライブラリ読込状態
  chartJsLoadingPromise: null,
  inflightJsonRequests: new Map(),

  // ランキング用 フィルタ・ソート・お気に入り状態
  currentSearchQuery: "",
  currentSortMode: "rank",
  showFavoritesOnly: false,
  favoriteSongKeys: new Set(),

  // 記事・コラム用 状態管理
  allArticlesData: [],
  currentArticleCategory: "all",
  currentArticleSearchQuery: "",
  currentOpenArticleId: null,
  articlesDataLoaded: false,
  articlesLoadingPromise: null
};
