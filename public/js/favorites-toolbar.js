/**
 * お気に入り（ローカルブックマーク）管理・検索/ソート/連続再生/SNSシェアツールバーモジュール
 */
import { OFFICIAL_SITE_URL, FAVORITES_STORAGE_KEY, state } from "./config-state.js";
import {
  getPrimarySongKey,
  getSongsArray,
  sanitizeYoutubeId,
  normalizePeriodString
} from "./utils.js";
import { showToast } from "./ui-common.js";

let onRankingChangeCallback = null;

function notifyRankingChange(explicitCallback) {
  const cb = typeof explicitCallback === "function" ? explicitCallback : onRankingChangeCallback;
  if (typeof cb === "function") {
    cb();
  }
}

/** localStorage からお気に入り楽曲キーを読み込む */
export function loadFavoritesFromStorage() {
  try {
    const raw = localStorage.getItem(FAVORITES_STORAGE_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) {
        state.favoriteSongKeys = new Set(arr);
      }
    }
  } catch (_) {
    state.favoriteSongKeys = new Set();
  }
  updateFavCountBadge();
}

/** お気に入り楽曲キーを localStorage へ保存する */
export function saveFavoritesToStorage() {
  try {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(Array.from(state.favoriteSongKeys)));
  } catch (_) {
    // ignore storage quota errors
  }
  updateFavCountBadge();
}

/** 指定楽曲がお気に入り登録済みかを判定する */
export function isSongFavorited(song) {
  const key = getPrimarySongKey(song);
  return key ? state.favoriteSongKeys.has(key) : false;
}

/** 指定楽曲キーのお気に入り状態を切り替え、必要に応じて再描画コールバックを通知する */
export function toggleFavoriteSong(songKey, onUpdate) {
  if (!songKey) return;
  if (state.favoriteSongKeys.has(songKey)) {
    state.favoriteSongKeys.delete(songKey);
    showToast("お気に入りから解除しました");
  } else {
    state.favoriteSongKeys.add(songKey);
    showToast("★ お気に入りに保存しました");
  }
  saveFavoritesToStorage();
  notifyRankingChange(onUpdate);
}

/** ヘッダー/ツールバーのお気に入り件数バッジとフィルタ状態を同期する */
export function updateFavCountBadge() {
  const countSpan = document.getElementById("fav-count-num");
  const favBtn = document.getElementById("fav-filter-btn");
  if (countSpan) {
    countSpan.textContent = String(state.favoriteSongKeys.size);
  }
  if (favBtn) {
    favBtn.classList.toggle("active", state.showFavoritesOnly);
    favBtn.setAttribute("aria-pressed", state.showFavoritesOnly ? "true" : "false");
  }
}

/** 検索・ソート・お気に入りフィルタ・YouTube連続再生・SNSシェアの便利ツールバーを初期化する */
export function initUtilityToolbar(onFilterChange) {
  if (typeof onFilterChange === "function") {
    onRankingChangeCallback = onFilterChange;
  }

  const searchInput = document.getElementById("ranking-search-input");
  const sortSelect = document.getElementById("ranking-sort-select");
  const favFilterBtn = document.getElementById("fav-filter-btn");
  const ytPlaylistBtn = document.getElementById("yt-playlist-btn");
  const shareXBtn = document.getElementById("share-x-btn");
  const copySummaryBtn = document.getElementById("copy-summary-btn");

  if (searchInput) {
    searchInput.addEventListener("input", function (e) {
      state.currentSearchQuery = (e.target.value || "").trim().toLowerCase();
      notifyRankingChange();
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", function (e) {
      state.currentSortMode = e.target.value || "rank";
      notifyRankingChange();
    });
  }

  if (favFilterBtn) {
    favFilterBtn.addEventListener("click", function () {
      state.showFavoritesOnly = !state.showFavoritesOnly;
      updateFavCountBadge();
      notifyRankingChange();
    });
  }

  if (ytPlaylistBtn) {
    ytPlaylistBtn.addEventListener("click", function () {
      const songs = getSongsArray(state.currentChartData);
      const ytIds = songs
        .slice(0, 20)
        .map(function (s) {
          return sanitizeYoutubeId(s.youtube_id);
        })
        .filter(Boolean);

      if (!ytIds.length) {
        showToast("再生可能なYouTube動画が見つかりません");
        return;
      }
      const playlistUrl = "https://www.youtube.com/watch_videos?video_ids=" + ytIds.join(",");
      window.open(playlistUrl, "_blank", "noopener,noreferrer");
    });
  }

  if (shareXBtn) {
    shareXBtn.addEventListener("click", function () {
      const text = buildChartSummaryText();
      const shareUrl =
        "https://twitter.com/intent/tweet?text=" +
        encodeURIComponent(text) +
        "&url=" +
        encodeURIComponent(OFFICIAL_SITE_URL);
      window.open(shareUrl, "_blank", "noopener,noreferrer");
    });
  }

  if (copySummaryBtn) {
    copySummaryBtn.addEventListener("click", async function () {
      const text = buildChartSummaryText() + "\n" + OFFICIAL_SITE_URL;
      try {
        await navigator.clipboard.writeText(text);
        showToast("📋 今週のランキング結果をコピーしました！");
      } catch (_) {
        showToast("コピーに失敗しました");
      }
    });
  }
}

/** SNSシェア・テキストコピー用のランキングサマリー文を生成する */
export function buildChartSummaryText() {
  if (!state.currentChartData) {
    return "週刊VOCALOID™複合ランキング TOP 20 #週刊VOCALOID複合ランキング #vocanew #ボカロ";
  }
  const period = normalizePeriodString(state.currentChartData.period || "");
  const top3 = getSongsArray(state.currentChartData).slice(0, 3);
  const lines = top3.map(function (s, i) {
    return (
      i +
      1 +
      "位: " +
      s.title +
      " / " +
      s.producer +
      " (" +
      Number(s.total_pt || 0).toLocaleString() +
      " pt)"
    );
  });
  return (
    "【週刊VOCALOID™複合ランキング】\n集計期間: " +
    period +
    "\n\n" +
    lines.join("\n") +
    "\n\n#週刊VOCALOID複合ランキング #ボカロ"
  );
}
