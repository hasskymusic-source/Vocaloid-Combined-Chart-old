/**
 * 汎用ユーティリティ・サニタイズ・日付/楽曲キー変換関数群
 */
import { MOBILE_MEDIA_QUERY } from "./config-state.js";

/** HTML特殊文字をエスケープする */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** スマートフォン表示幅かどうかを判定する */
export function isSmartphoneViewport() {
  return Boolean(window.matchMedia && window.matchMedia(MOBILE_MEDIA_QUERY).matches);
}

/** ブラウザのデータセーバー設定が有効かを判定する */
export function isDataSaverEnabled() {
  return Boolean(navigator.connection && navigator.connection.saveData);
}

/** ローカルプレビュー環境 (localhost / 127.0.0.1) かを判定する */
export function isLocalOwnerPreview() {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1";
}

/** チャートデータが一般公開時刻を過ぎているかを判定する */
export function isChartReleasedForPublic(chartData) {
  if (isLocalOwnerPreview()) return true;
  if (!chartData || typeof chartData !== "object") return true;

  let releaseMs = null;
  if (chartData.publishAt && typeof chartData.publishAt === "string") {
    const parsed = Date.parse(chartData.publishAt);
    if (!isNaN(parsed)) {
      releaseMs = parsed;
    }
  }

  if (releaseMs === null) {
    const dateStr = chartData.publishDate || chartData.archiveId || "";
    const m = String(dateStr).trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) {
      releaseMs = Date.parse(m[1] + "-" + m[2] + "-" + m[3] + "T13:00:00+09:00");
    }
  }

  if (releaseMs === null || isNaN(releaseMs)) return true;
  return Date.now() >= releaseMs;
}

/** 記事データが一般公開可能かを判定する */
export function isArticleReleasedForPublic(article) {
  if (!article || typeof article !== "object") return false;
  if (isLocalOwnerPreview()) {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("preview") === "1") return true;
  }
  const status = String(article.status || "published").toLowerCase();
  if (status === "draft") return false;

  if (article.publishAt && typeof article.publishAt === "string") {
    const parsed = Date.parse(article.publishAt);
    if (!isNaN(parsed) && Date.now() < parsed) {
      return false;
    }
  }
  return true;
}

/** YouTube動画IDを検証して安全なIDのみ返す */
export function sanitizeYoutubeId(rawId) {
  if (!rawId || typeof rawId !== "string") return "";
  const trimmed = rawId.trim();
  return /^[A-Za-z0-9_-]{6,20}$/.test(trimmed) ? trimmed : "";
}

/** ニコニコ動画IDを検証して安全なIDのみ返す */
export function sanitizeNiconicoId(rawId) {
  if (!rawId || typeof rawId !== "string") return "";
  const trimmed = rawId.trim();
  return /^(sm|nm|so)?[0-9]{1,16}$/i.test(trimmed) ? trimmed : "";
}

/** 許可ホストまたはYouTubeフォールバックから安全なサムネイルURLを返す */
export function sanitizeThumbnailUrl(rawUrl, fallbackYtId) {
  if (rawUrl && typeof rawUrl === "string") {
    try {
      const parsed = new URL(rawUrl, window.location.origin);
      const allowedHosts = [
        "i.ytimg.com",
        "img.youtube.com",
        "img.cdn.nimg.jp",
        "nicovideo.cdn.nimg.jp",
        window.location.hostname
      ];
      if (parsed.protocol === "https:" && allowedHosts.indexOf(parsed.hostname) !== -1) {
        return parsed.href;
      }
      if (parsed.origin === window.location.origin) {
        return parsed.href;
      }
    } catch (_) {
      // ignore invalid URL
    }
  }
  const safeYt = sanitizeYoutubeId(fallbackYtId);
  return safeYt ? "https://i.ytimg.com/vi/" + safeYt + "/mqdefault.jpg" : "";
}

/** 記事サムネイルやアイコン用の安全な画像URLを返す */
export function sanitizeSafeImageUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== "string") return "";
  const trimmed = rawUrl.trim();
  if (trimmed.indexOf("data:image/") === 0) return trimmed;
  if (trimmed.indexOf("./") === 0 || trimmed.indexOf("/") === 0) return trimmed;
  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (parsed.protocol === "https:" || parsed.origin === window.location.origin) {
      return parsed.href;
    }
  } catch (_) {
    // ignore invalid URL
  }
  return "";
}

/** アーカイブJSONファイル名を検証・サニタイズする */
export function sanitizeArchiveFilename(rawVal) {
  if (!rawVal || typeof rawVal !== "string") return "";
  const base = rawVal.trim().replace(/^.*[/\\]/, "");
  const withExt = base.endsWith(".json") ? base : base + ".json";
  return /^[A-Za-z0-9_.-]+\.json$/.test(withExt) && withExt.indexOf("..") === -1 ? withExt : "";
}

/** お気に入り保存等に使用する楽曲の主識別キーを生成する */
export function getPrimarySongKey(song) {
  if (!song || typeof song !== "object") return "";
  return String(
    song.song_id ||
      song.id ||
      song.youtube_id ||
      song.niconico_id ||
      (song.title || "") + "__" + (song.producer || "")
  );
}

/** チャートデータから楽曲配列を正規化して取り出す */
export function getSongsArray(chartData) {
  if (!chartData) return [];
  if (Array.isArray(chartData)) return chartData;
  if (Array.isArray(chartData.ranking)) return chartData.ranking;
  if (Array.isArray(chartData.songs)) return chartData.songs;
  return [];
}

/** 過去履歴照合に使用する楽曲の複数識別キー一覧を返す */
export function getSongIdentityKeys(song) {
  if (!song || typeof song !== "object") return [];
  const keys = [];
  if (song.song_id) keys.push("id:" + song.song_id);
  if (song.id) keys.push("id:" + song.id);
  if (song.youtube_id) keys.push("yt:" + song.youtube_id);
  if (song.niconico_id) keys.push("nc:" + song.niconico_id);
  if (song.title && song.producer) keys.push("tp:" + song.title + "__" + song.producer);
  return keys;
}

/** 集計期間文字列を「YYYY/MM/DD - YYYY/MM/DD」形式へ正規化する */
export function normalizePeriodString(periodStr) {
  if (!periodStr || typeof periodStr !== "string") return "";
  const match = periodStr.match(
    /(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\s*[\-~〜]\s*(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/
  );
  if (!match) return periodStr;

  const y1 = parseInt(match[1], 10);
  const m1 = parseInt(match[2], 10);
  const d1 = parseInt(match[3], 10);
  const y2 = parseInt(match[4], 10);
  const m2 = parseInt(match[5], 10);
  const d2 = parseInt(match[6], 10);

  const startDt = new Date(Date.UTC(y1, m1 - 1, d1));
  const endDt = new Date(Date.UTC(y2, m2 - 1, d2));
  const diffDays = Math.round((endDt - startDt) / 86400000);

  if (diffDays === 7) {
    endDt.setUTCDate(endDt.getUTCDate() - 1);
  }

  const fmt = function (dt) {
    const yy = dt.getUTCFullYear();
    const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(dt.getUTCDate()).padStart(2, "0");
    return yy + "/" + mm + "/" + dd;
  };
  return fmt(startDt) + " - " + fmt(endDt);
}

/** チャートデータから更新日の「YYYY/MM/DD」文字列を抽出する */
export function extractUpdateDateString(data) {
  const rawUpdate = data.publishDate || data.updated_at || data.published_at || "";
  if (rawUpdate && typeof rawUpdate === "string") {
    const m = rawUpdate.match(/(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
    if (m) {
      return m[1] + "/" + String(m[2]).padStart(2, "0") + "/" + String(m[3]).padStart(2, "0");
    }
  }
  return "";
}
