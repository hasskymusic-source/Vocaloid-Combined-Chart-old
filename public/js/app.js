import {
  OFFICIAL_SITE_URL,
  LAST_KNOWN_CHART_STORAGE_KEY,
  ARCHIVE_HISTORY_SESSION_KEY,
  DEFAULT_PAGE_TITLE,
  DEFAULT_META_DESC,
  state
} from "./config-state.js";
import {
  escapeHtml,
  isSmartphoneViewport,
  isDataSaverEnabled,
  isLocalOwnerPreview,
  isChartReleasedForPublic,
  isArticleReleasedForPublic,
  sanitizeYoutubeId,
  sanitizeNiconicoId,
  sanitizeThumbnailUrl,
  sanitizeSafeImageUrl,
  sanitizeArchiveFilename,
  getPrimarySongKey,
  getSongsArray,
  getSongIdentityKeys,
  normalizePeriodString,
  extractUpdateDateString
} from "./utils.js";
import { ensureChartJsLoaded, fetchJsonWithFallback } from "./api.js";
import { parseArticleBodyHtml } from "./article-parser.js";
import {
  initSiteViewCounter,
  showToast,
  initBackToTopButton,
  initScrollHints,
  refreshAllScrollHints
} from "./ui-common.js";
import {
  getPointsBreakdown,
  formatPointRatioHTML,
  renderTop10InsightChart,
  renderInsightTable,
  renderCommentaryView
} from "./insight-view.js";
import {
  loadFavoritesFromStorage,
  isSongFavorited,
  toggleFavoriteSong,
  initUtilityToolbar
} from "./favorites-toolbar.js";

window.__VOCALOID_APP_LOADED__ = true;

function startApp() {
  loadFavoritesFromStorage();
  initTabs();
  initUtilityToolbar(function () {
    if (state.currentChartData) {
      renderRankingView(getSongsArray(state.currentChartData));
    }
  });
  initRankingEventDelegation();
  initScrollHints();
  initBackToTopButton();
  initSiteViewCounter();
  initChartApp();
  initArticlesSystem();

  if (!isSmartphoneViewport() && !isDataSaverEnabled()) {
    const idleFn =
      window.requestIdleCallback ||
      function (cb) {
        setTimeout(cb, 1500);
      };
    idleFn(function () {
      ensureChartJsLoaded();
    });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startApp);
} else {
  startApp();
}

function initRankingEventDelegation() {
  const container = document.getElementById("ranking-container");
  if (!container) return;

  container.addEventListener("click", function (e) {
    const detailBtn = e.target.closest(".detail-toggle-btn");
    if (detailBtn) {
      e.stopPropagation();
      const rank = parseInt(detailBtn.getAttribute("data-rank"), 10);
      if (!isNaN(rank)) {
        window.toggleRankDetail(rank);
      }
      return;
    }

    const favBtn = e.target.closest(".fav-star-btn");
    if (favBtn) {
      e.stopPropagation();
      const songKey = favBtn.getAttribute("data-song-key");
      toggleFavoriteSong(songKey);
      return;
    }

    const shareSongBtn = e.target.closest(".share-song-x-btn");
    if (shareSongBtn) {
      e.stopPropagation();
      const rank = shareSongBtn.getAttribute("data-rank");
      const title = shareSongBtn.getAttribute("data-title");
      const producer = shareSongBtn.getAttribute("data-producer");
      const pt = shareSongBtn.getAttribute("data-pt");
      const text =
        "『" +
        title +
        "』(" +
        producer +
        ") が「週刊VOCALOID™複合ランキング」で今週 " +
        rank +
        "位 (" +
        pt +
        " pt) にランクイン！\n#週刊VOCALOID複合ランキング #ボカロ";
      const shareUrl =
        "https://twitter.com/intent/tweet?text=" +
        encodeURIComponent(text) +
        "&url=" +
        encodeURIComponent(OFFICIAL_SITE_URL);
      window.open(shareUrl, "_blank", "noopener,noreferrer");
    }
  });
}

function activateTabById(targetId) {
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach(function (b) {
    const isMatch = b.getAttribute("data-tab") === targetId;
    b.classList.toggle("active", isMatch);
    if (isMatch && typeof b.scrollIntoView === "function") {
      b.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  });

  tabContents.forEach(function (c) {
    c.classList.toggle("active", c.id === targetId);
  });

  if (targetId === "tab-insight" && state.currentChartData) {
    ensureChartJsLoaded().then(function () {
      requestAnimationFrame(function () {
        setTimeout(function () {
          renderTop10InsightChart(getSongsArray(state.currentChartData));
          refreshAllScrollHints();
        }, 20);
      });
    });
  } else {
    requestAnimationFrame(function () {
      refreshAllScrollHints();
    });
  }
}

function initTabs() {
  const tabButtons = document.querySelectorAll(".tab-btn");
  tabButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const targetId = btn.getAttribute("data-tab");
      if (!targetId) return;
      activateTabById(targetId);

      const articlesTabId = getArticlesTabId();
      if (targetId !== articlesTabId && window.location.hash.indexOf("#article=") === 0) {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    });
  });
}

async function initChartApp() {
  await loadArchiveIndexOnly();
  await loadAndRenderChart();

  try {
    const songs = getSongsArray(state.currentChartData);
    const needsHistoryEnrich = songs.some(function (s) {
      return typeof s.chart_in_count !== "number" || s.chart_in_count < 1;
    });

    if (needsHistoryEnrich) {
      await ensureFullArchiveHistoryLoaded();
      if (state.currentChartData) {
        enrichWithHistory(state.currentChartData);
        renderAllViews(state.currentChartData);
      }
    }
  } catch (err) {
    console.warn("アーカイブ履歴の補完をスキップしました:", err);
  }
}

async function loadArchiveIndexOnly() {
  const indexData = await fetchJsonWithFallback(
    [
      "./data/archives/archive_index.json",
      "./data/archive_index.json",
      "public/data/archives/archive_index.json",
      "public/data/archive_index.json"
    ],
    "no-cache"
  );

  const selectEl = document.getElementById("archive-select");
  const rawArchiveList = Array.isArray(indexData)
    ? indexData
    : indexData && Array.isArray(indexData.archives)
    ? indexData.archives
    : [];

  const archiveList = rawArchiveList.filter(function (item) {
    if (isLocalOwnerPreview()) return true;
    if (typeof item === "string") {
      const stem = item.replace(/\.json$/i, "");
      return isChartReleasedForPublic({ publishDate: stem });
    }
    return isChartReleasedForPublic(item);
  });

  state.cachedArchiveListMeta = archiveList;
  if (!archiveList.length) {
    return;
  }

  if (selectEl && selectEl.options.length <= 1) {
    archiveList.forEach(function (item) {
      const fileVal =
        typeof item === "string"
          ? item
          : item.file || item.path || (item.archiveId ? item.archiveId + ".json" : item.id);
      let labelText =
        typeof item === "string"
          ? item
          : item.label || item.period || item.publishDate || item.archiveId || item.id;
      if (labelText && typeof labelText === "string") {
        labelText = labelText.replace(
          /(\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}\s*[\-~〜]\s*\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})/,
          function (m) {
            return normalizePeriodString(m);
          }
        );
      }
      const safeFile = sanitizeArchiveFilename(fileVal);
      if (!safeFile) return;
      const opt = document.createElement("option");
      opt.value = safeFile;
      opt.textContent = labelText;
      selectEl.appendChild(opt);
    });

    selectEl.addEventListener("change", async function (e) {
      const val = e.target.value;
      if (val === "latest") {
        await loadAndRenderChart();
      } else {
        const cleanFile = sanitizeArchiveFilename(val);
        if (!cleanFile) return;
        const archiveData = await fetchJsonWithFallback(
          ["./data/archives/" + cleanFile, "public/data/archives/" + cleanFile],
          "default"
        );
        if (archiveData && isChartReleasedForPublic(archiveData)) {
          const archiveSongs = getSongsArray(archiveData);
          const archiveNeedsEnrich = archiveSongs.some(function (s) {
            return typeof s.chart_in_count !== "number" || s.chart_in_count < 1;
          });
          if (archiveNeedsEnrich) {
            await ensureFullArchiveHistoryLoaded();
            enrichWithHistory(archiveData);
          }
          state.currentChartData = archiveData;
          renderAllViews(archiveData);
        }
      }
    });
  }
}

async function ensureFullArchiveHistoryLoaded() {
  if (state.archiveHistoryLoaded || !state.cachedArchiveListMeta.length) return;
  state.archiveHistoryLoaded = true;

  try {
    const cachedRaw = sessionStorage.getItem(ARCHIVE_HISTORY_SESSION_KEY);
    if (cachedRaw) {
      const parsed = JSON.parse(cachedRaw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        state.archiveHistoryCache = parsed;
        return;
      }
    }
  } catch (_) {
    // ignore sessionStorage error
  }

  const loadedArchives = [];
  for (let i = 0; i < state.cachedArchiveListMeta.length; i++) {
    const item = state.cachedArchiveListMeta[i];
    const rawFile =
      typeof item === "string"
        ? item
        : item.file || item.path || (item.archiveId ? item.archiveId + ".json" : item.id);
    const cleanFile = sanitizeArchiveFilename(rawFile);
    if (!cleanFile) continue;
    const data = await fetchJsonWithFallback(
      ["./data/archives/" + cleanFile, "public/data/archives/" + cleanFile],
      "default"
    );
    if (data && getSongsArray(data).length > 0 && isChartReleasedForPublic(data)) {
      loadedArchives.push(data);
    }
  }
  state.archiveHistoryCache = loadedArchives;

  try {
    sessionStorage.setItem(ARCHIVE_HISTORY_SESSION_KEY, JSON.stringify(loadedArchives));
  } catch (_) {
    // ignore quota error
  }
}

function enrichWithHistory(chartData) {
  const songs = getSongsArray(chartData);
  if (!songs.length || !state.archiveHistoryCache.length) return;

  const targetKey =
    chartData.archiveId || chartData.publishDate || chartData.period || chartData.updated_at || "";

  const olderCharts = state.archiveHistoryCache.filter(function (c) {
    const p = c.archiveId || c.publishDate || c.period || c.updated_at || "";
    return p && targetKey ? p < targetKey : false;
  });

  const prevChart = olderCharts.length > 0 ? olderCharts[olderCharts.length - 1] : null;

  songs.forEach(function (song) {
    const keys = getSongIdentityKeys(song);

    if (typeof song.chart_in_count !== "number" || song.chart_in_count < 1) {
      let count = 1;
      olderCharts.forEach(function (past) {
        const matched = getSongsArray(past)
          .slice(0, 20)
          .some(function (ps) {
            const pKeys = getSongIdentityKeys(ps);
            return keys.some(function (k) {
              return pKeys.indexOf(k) !== -1;
            });
          });
        if (matched) count += 1;
      });
      song.chart_in_count = count;
    }

    if (song.prev_total_pt === undefined && prevChart) {
      const prevSong = getSongsArray(prevChart).find(function (ps) {
        const pKeys = getSongIdentityKeys(ps);
        return keys.some(function (k) {
          return pKeys.indexOf(k) !== -1;
        });
      });
      if (prevSong && typeof prevSong.total_pt === "number") {
        song.prev_total_pt = prevSong.total_pt;
      }
    }

    if (
      (song.pt_ratio === undefined || song.pt_ratio === null) &&
      typeof song.prev_total_pt === "number" &&
      song.prev_total_pt > 0
    ) {
      song.pt_ratio = Math.round((song.total_pt / song.prev_total_pt) * 100);
    }
  });
}

async function loadLatestReleasedArchiveFallback() {
  for (let i = 0; i < state.cachedArchiveListMeta.length; i++) {
    const item = state.cachedArchiveListMeta[i];
    const rawFile =
      typeof item === "string"
        ? item
        : item.file || item.path || (item.archiveId ? item.archiveId + ".json" : item.id);
    const cleanFile = sanitizeArchiveFilename(rawFile);
    if (!cleanFile) continue;
    const archiveData = await fetchJsonWithFallback(
      ["./data/archives/" + cleanFile, "public/data/archives/" + cleanFile],
      "no-cache"
    );
    if (archiveData && isChartReleasedForPublic(archiveData)) {
      return archiveData;
    }
  }
  return null;
}

async function loadAndRenderChart() {
  const candidateUrls = isLocalOwnerPreview()
    ? [
        "./data/latest_ranking.json",
        "./data/drafts/weekly_draft.json",
        "./data/weekly_draft.json",
        "public/data/latest_ranking.json"
      ]
    : [
        "./data/latest_ranking.json",
        "data/latest_ranking.json",
        "public/data/latest_ranking.json",
        "latest_ranking.json"
      ];

  let data = await fetchJsonWithFallback(candidateUrls, "no-cache");

  if (data && !isChartReleasedForPublic(data)) {
    const fallbackReleased = await loadLatestReleasedArchiveFallback();
    if (fallbackReleased) {
      data = fallbackReleased;
    }
  }

  if (data) {
    try {
      localStorage.setItem(LAST_KNOWN_CHART_STORAGE_KEY, JSON.stringify(data));
    } catch (_) {
      // ignore storage quota errors
    }
  } else {
    try {
      const cachedStr = localStorage.getItem(LAST_KNOWN_CHART_STORAGE_KEY);
      if (cachedStr) {
        const parsedCache = JSON.parse(cachedStr);
        if (isChartReleasedForPublic(parsedCache)) {
          data = parsedCache;
          showToast("回線混雑のためキャッシュデータを表示しています");
        }
      }
    } catch (_) {
      data = null;
    }
  }

  if (!data) {
    const container = document.getElementById("ranking-container");
    if (container) {
      container.innerHTML =
        '<div class="error-state">ランキングデータの読み込みに失敗しました。再読み込みをお試しください。</div>';
    }
    return;
  }

  enrichWithHistory(data);
  state.currentChartData = data;
  renderAllViews(data);
}

function renderAllViews(data) {
  const periodEl = document.getElementById("chart-period") || document.getElementById("chart-title");
  if (periodEl) {
    const cleanPeriod = normalizePeriodString(data.period || "");
    const updateDate = extractUpdateDateString(data);
    if (cleanPeriod && updateDate) {
      periodEl.textContent = cleanPeriod + " / 更新: " + updateDate;
    } else if (cleanPeriod) {
      periodEl.textContent = cleanPeriod;
    } else if (updateDate) {
      periodEl.textContent = "更新: " + updateDate;
    } else {
      periodEl.textContent = "最新チャート";
    }
  }

  if (data.milestone_message) {
    const bannerEl = document.getElementById("milestone-banner");
    const bannerTextEl = document.getElementById("milestone-text");
    if (bannerEl && bannerTextEl) {
      bannerTextEl.textContent = data.milestone_message;
      bannerEl.style.display = "block";
    }
  }

  const ranking = getSongsArray(data);
  renderRankingView(ranking);
  renderInsightTable(ranking);
  renderCommentaryView(data, ranking);

  const insightSection = document.getElementById("tab-insight");
  if (insightSection && insightSection.classList.contains("active")) {
    ensureChartJsLoaded().then(function () {
      renderTop10InsightChart(ranking);
    });
  }

  requestAnimationFrame(function () {
    refreshAllScrollHints();
  });
}

function formatRankDiffBadge(song) {
  const prev = parseInt(song.prev_rank !== undefined ? song.prev_rank : song.prevRank, 10);
  const curr = parseInt(song.rank, 10);
  if (!prev || isNaN(prev)) {
    return '<span class="rank-diff diff-new">NEW</span>';
  }
  if (prev > curr) {
    return '<span class="rank-diff diff-up">▲' + (prev - curr) + " (前週" + prev + "位)</span>";
  }
  if (prev < curr) {
    return '<span class="rank-diff diff-down">▼' + (curr - prev) + " (前週" + prev + "位)</span>";
  }
  return '<span class="rank-diff diff-stay">→ KEEP (前週' + prev + "位)</span>";
}

function getOptimizedThumbnailAttrs(song, index) {
  const safeThumbUrl = sanitizeThumbnailUrl(song.thumbnail, song.youtube_id);
  if (!safeThumbUrl) return null;

  const isAboveFold = index < 3;
  const loadingAttr = isAboveFold ? "eager" : "lazy";
  const priorityAttr = isAboveFold ? 'fetchpriority="high"' : 'fetchpriority="low"';

  return {
    url: safeThumbUrl,
    loadingAttr: loadingAttr,
    priorityAttr: priorityAttr
  };
}

function getFilteredAndSortedSongs(ranking) {
  let list = ranking.slice(0, 20).map(function (s, i) {
    return Object.assign({}, s, {
      _origRank: parseInt(s.rank, 10) || i + 1
    });
  });

  if (state.showFavoritesOnly) {
    list = list.filter(function (s) {
      return isSongFavorited(s);
    });
  }

  if (state.currentSearchQuery) {
    list = list.filter(function (s) {
      const hay = ((s.title || "") + " " + (s.producer || "") + " " + (s.vocal || "")).toLowerCase();
      return hay.indexOf(state.currentSearchQuery) !== -1;
    });
  }

  if (state.currentSortMode === "pt_ratio") {
    list.sort(function (a, b) {
      return (b.pt_ratio || 0) - (a.pt_ratio || 0);
    });
  } else if (state.currentSortMode === "chart_in") {
    list.sort(function (a, b) {
      return (b.chart_in_count || 1) - (a.chart_in_count || 1);
    });
  } else if (state.currentSortMode === "yt_share") {
    list.sort(function (a, b) {
      const ba = getPointsBreakdown(a);
      const bb = getPointsBreakdown(b);
      return bb.yt_total / bb.calcSum - ba.yt_total / ba.calcSum;
    });
  } else if (state.currentSortMode === "nc_share") {
    list.sort(function (a, b) {
      const ba = getPointsBreakdown(a);
      const bb = getPointsBreakdown(b);
      return bb.nc_total / bb.calcSum - ba.nc_total / ba.calcSum;
    });
  } else {
    list.sort(function (a, b) {
      return a._origRank - b._origRank;
    });
  }

  return list;
}

function buildRankCardHtml(song, idx) {
  const rankNum = song._origRank || parseInt(song.rank, 10) || idx + 1;
  const bd = getPointsBreakdown(song);
  const raw = song.raw || {};
  const denom = bd.calcSum;

  const pYtViews = ((bd.yt_views / denom) * 100).toFixed(2);
  const pYtLikes = ((bd.yt_likes / denom) * 100).toFixed(2);
  const pYtComments = ((bd.yt_comments / denom) * 100).toFixed(2);
  const pNcViews = ((bd.nc_views / denom) * 100).toFixed(2);
  const pNcMylists = ((bd.nc_mylists / denom) * 100).toFixed(2);
  const pNcComments = ((bd.nc_comments / denom) * 100).toFixed(2);

  const ytPercent = bd.total_pt > 0 ? ((bd.yt_total / bd.total_pt) * 100).toFixed(1) : "0.0";
  const ncPercent = bd.total_pt > 0 ? ((bd.nc_total / bd.total_pt) * 100).toFixed(1) : "0.0";
  const chartInCount = parseInt(song.chart_in_count, 10) || 1;
  const thumbInfo = getOptimizedThumbnailAttrs(song, idx);
  const safeYtId = sanitizeYoutubeId(song.youtube_id);
  const safeNcId = sanitizeNiconicoId(song.niconico_id);
  const songKey = getPrimarySongKey(song);
  const isFav = isSongFavorited(song);

  let thumbHtml = "";
  if (thumbInfo) {
    thumbHtml =
      '<div class="rank-thumb-col">' +
      '<img src="' +
      escapeHtml(thumbInfo.url) +
      '" alt="' +
      escapeHtml(song.title) +
      '" class="rank-thumb" width="112" height="63" loading="' +
      thumbInfo.loadingAttr +
      '" decoding="async" referrerpolicy="no-referrer" ' +
      thumbInfo.priorityAttr +
      " />" +
      "</div>";
  }

  const vocalHtml = song.vocal
    ? '<span class="song-vocal">feat. ' + escapeHtml(song.vocal) + "</span>"
    : "";

  const ytLinkHtml = safeYtId
    ? '<a href="https://www.youtube.com/watch?v=' +
      encodeURIComponent(safeYtId) +
      '" target="_blank" rel="noopener noreferrer" class="video-link yt-link">▶ YouTubeで視聴する</a>'
    : "";

  const ncLinkHtml = safeNcId
    ? '<a href="https://www.nicovideo.jp/watch/' +
      encodeURIComponent(safeNcId) +
      '" target="_blank" rel="noopener noreferrer" class="video-link nc-link">▶ ニコニコ動画で視聴する</a>'
    : "";

  const commentaryHtml = song.commentary
    ? '<div class="commentary-box"><h5>楽曲解説・チャート分析</h5><p>' +
      escapeHtml(song.commentary).replace(/\n/g, "<br>") +
      "</p></div>"
    : "";

  const favClass = isFav ? "favorited" : "";
  const favTitle = isFav ? "お気に入り解除" : "お気に入りに保存";
  const favSymbol = isFav ? "★" : "☆";

  return (
    '<article class="rank-card rank-' +
    rankNum +
    '" data-rank="' +
    rankNum +
    '">' +
    '<div class="rank-card-summary">' +
    '<div class="rank-number-col">' +
    '<span class="rank-number">' +
    rankNum +
    "<small>位</small></span>" +
    formatRankDiffBadge(song) +
    '<span class="chart-in-mini">' +
    chartInCount +
    "週目</span>" +
    "</div>" +
    thumbHtml +
    '<div class="rank-info-col">' +
    '<div class="song-title-row">' +
    '<h3 class="song-title">' +
    escapeHtml(song.title) +
    "</h3>" +
    '<div class="card-inline-actions">' +
    '<button type="button" class="fav-star-btn ' +
    favClass +
    '" data-song-key="' +
    escapeHtml(songKey) +
    '" title="' +
    favTitle +
    '" aria-label="お気に入り">' +
    favSymbol +
    "</button>" +
    '<button type="button" id="detail-btn-' +
    rankNum +
    '" class="detail-toggle-btn" data-rank="' +
    rankNum +
    '">詳細を見る ▾</button>' +
    "</div>" +
    "</div>" +
    '<div class="song-meta">' +
    '<span class="song-producer">' +
    escapeHtml(song.producer) +
    "</span>" +
    vocalHtml +
    "</div>" +
    '<div class="metric-stacked-bar">' +
    '<div class="bar-seg seg-yt-views" style="width: ' +
    pYtViews +
    '%" title="YouTube再生: ' +
    Number(bd.yt_views).toLocaleString() +
    " pt (" +
    pYtViews +
    '%)"></div>' +
    '<div class="bar-seg seg-yt-likes" style="width: ' +
    pYtLikes +
    '%" title="YouTube高評価: ' +
    Number(bd.yt_likes).toLocaleString() +
    " pt (" +
    pYtLikes +
    '%)"></div>' +
    '<div class="bar-seg seg-yt-comments" style="width: ' +
    pYtComments +
    '%" title="YouTubeコメント: ' +
    Number(bd.yt_comments).toLocaleString() +
    " pt (" +
    pYtComments +
    '%)"></div>' +
    '<div class="bar-seg seg-nc-views" style="width: ' +
    pNcViews +
    '%" title="ニコ動再生: ' +
    Number(bd.nc_views).toLocaleString() +
    " pt (" +
    pNcViews +
    '%)"></div>' +
    '<div class="bar-seg seg-nc-mylists" style="width: ' +
    pNcMylists +
    '%" title="ニコ動マイリス: ' +
    Number(bd.nc_mylists).toLocaleString() +
    " pt (" +
    pNcMylists +
    '%)"></div>' +
    '<div class="bar-seg seg-nc-comments" style="width: ' +
    pNcComments +
    '%" title="ニコ動コメント: ' +
    Number(bd.nc_comments).toLocaleString() +
    " pt (" +
    pNcComments +
    '%)"></div>' +
    "</div>" +
    "</div>" +
    '<div class="rank-points-col">' +
    '<div class="total-points">' +
    Number(bd.total_pt).toLocaleString() +
    " <small>pt</small></div>" +
    '<div class="points-sub-row">' +
    "<span>前週比: " +
    formatPointRatioHTML(song) +
    "</span>" +
    '<span class="platform-split-text">YT ' +
    ytPercent +
    "% / NC " +
    ncPercent +
    "%</span>" +
    "</div>" +
    "</div>" +
    "</div>" +
    '<div id="detail-panel-' +
    rankNum +
    '" class="rank-detail-panel">' +
    '<div class="detail-grid">' +
    '<div class="detail-box yt-detail-box">' +
    "<h4>YouTube 指標内訳 (" +
    Number(bd.yt_total).toLocaleString() +
    " pt / " +
    ytPercent +
    "%)</h4>" +
    "<ul>" +
    '<li><span><i class="legend-dot seg-yt-views"></i>週間再生数:</span> <strong>+' +
    Number(raw.yt_views || 0).toLocaleString() +
    "</strong> (" +
    Number(bd.yt_views).toLocaleString() +
    " pt)</li>" +
    '<li><span><i class="legend-dot seg-yt-likes"></i>週間高評価数:</span> <strong>+' +
    Number(raw.yt_likes || 0).toLocaleString() +
    "</strong> (" +
    Number(bd.yt_likes).toLocaleString() +
    " pt)</li>" +
    '<li><span><i class="legend-dot seg-yt-comments"></i>週間コメント数:</span> <strong>+' +
    Number(raw.yt_comments || 0).toLocaleString() +
    "</strong> (" +
    Number(bd.yt_comments).toLocaleString() +
    " pt)</li>" +
    "</ul>" +
    ytLinkHtml +
    "</div>" +
    '<div class="detail-box nc-detail-box">' +
    "<h4>ニコニコ動画 指標内訳 (" +
    Number(bd.nc_total).toLocaleString() +
    " pt / " +
    ncPercent +
    "%)</h4>" +
    "<ul>" +
    '<li><span><i class="legend-dot seg-nc-views"></i>週間再生数:</span> <strong>+' +
    Number(raw.nc_views || 0).toLocaleString() +
    "</strong> (" +
    Number(bd.nc_views).toLocaleString() +
    " pt)</li>" +
    '<li><span><i class="legend-dot seg-nc-mylists"></i>週間マイリスト数:</span> <strong>+' +
    Number(bd.rawNcMylist).toLocaleString() +
    "</strong> (" +
    Number(bd.nc_mylists).toLocaleString() +
    " pt)</li>" +
    '<li><span><i class="legend-dot seg-nc-comments"></i>週間コメント数:</span> <strong>+' +
    Number(raw.nc_comments || 0).toLocaleString() +
    "</strong> (" +
    Number(bd.nc_comments).toLocaleString() +
    " pt)</li>" +
    "</ul>" +
    ncLinkHtml +
    "</div>" +
    "</div>" +
    '<div class="detail-share-row">' +
    '<button type="button" class="share-song-x-btn" data-rank="' +
    rankNum +
    '" data-title="' +
    escapeHtml(song.title) +
    '" data-producer="' +
    escapeHtml(song.producer) +
    '" data-pt="' +
    Number(bd.total_pt).toLocaleString() +
    '">𝕏 この楽曲のランクインをシェアする</button>' +
    "</div>" +
    commentaryHtml +
    "</div>" +
    "</article>"
  );
}

function renderRankingView(ranking) {
  const container = document.getElementById("ranking-container");
  if (!container) return;

  if (!ranking.length) {
    container.innerHTML = '<div class="empty-state">表示できるランキングデータがありません。</div>';
    return;
  }

  const displayList = getFilteredAndSortedSongs(ranking);
  if (!displayList.length) {
    container.innerHTML = '<div class="empty-state">条件に一致する楽曲が見つかりませんでした。</div>';
    return;
  }

  const htmlParts = [];
  for (let i = 0; i < displayList.length; i++) {
    htmlParts.push(buildRankCardHtml(displayList[i], i));
  }
  container.innerHTML = htmlParts.join("");
}

window.toggleRankDetail = function (rank, event) {
  if (event) {
    event.stopPropagation();
  }
  const safeRank = parseInt(rank, 10);
  if (isNaN(safeRank)) return;

  const panel = document.getElementById("detail-panel-" + safeRank);
  const btn = document.getElementById("detail-btn-" + safeRank);
  if (panel) {
    const isOpen = panel.classList.toggle("open");
    if (btn) {
      btn.textContent = isOpen ? "閉じる ▴" : "詳細を見る ▾";
      btn.classList.toggle("open", isOpen);
    }
    if (isOpen && isSmartphoneViewport()) {
      setTimeout(function () {
        const rect = panel.getBoundingClientRect();
        if (rect.bottom > window.innerHeight) {
          panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }, 60);
    }
  }
};

/* ==========================================================================
   5. 「記事・コラム」システム（Billboard Japan × ソシャゲなう風＋左右対話システム）
   ========================================================================== */

function getArticlesTabId() {
  const candidates = ["tab-articles", "tab-columns", "tab-column"];
  for (let i = 0; i < candidates.length; i++) {
    if (document.getElementById(candidates[i])) {
      return candidates[i];
    }
  }
  const buttons = document.querySelectorAll(".tab-btn");
  for (let j = 0; j < buttons.length; j++) {
    const txt = buttons[j].textContent || "";
    if (txt.indexOf("記事") !== -1 || txt.indexOf("コラム") !== -1) {
      return buttons[j].getAttribute("data-tab") || "tab-articles";
    }
  }
  return "tab-articles";
}

function ensureArticlesTabStructure() {
  let tabId = getArticlesTabId();
  let sectionEl = document.getElementById(tabId);

  if (!sectionEl) {
    tabId = "tab-articles";
    const tabNav = document.getElementById("tab-nav");
    const methodBtn = tabNav ? tabNav.querySelector('[data-tab="tab-method"]') : null;
    if (tabNav && !tabNav.querySelector('[data-tab="' + tabId + '"]')) {
      const newBtn = document.createElement("button");
      newBtn.className = "tab-btn";
      newBtn.setAttribute("data-tab", tabId);
      newBtn.textContent = "記事・コラム";
      if (methodBtn) {
        tabNav.insertBefore(newBtn, methodBtn);
      } else {
        tabNav.appendChild(newBtn);
      }
      newBtn.addEventListener("click", function () {
        activateTabById(tabId);
      });
    }

    const mainContainer = document.querySelector(".main-container") || document.body;
    const methodSec = document.getElementById("tab-method");
    sectionEl = document.createElement("section");
    sectionEl.id = tabId;
    sectionEl.className = "tab-content";
    if (methodSec && methodSec.parentElement === mainContainer) {
      mainContainer.insertBefore(sectionEl, methodSec);
    } else {
      mainContainer.appendChild(sectionEl);
    }
  }

  const hasExistingGrid = Boolean(
    sectionEl.querySelector("#articles-grid") ||
      sectionEl.querySelector("#column-grid") ||
      sectionEl.querySelector("#articles-container") ||
      sectionEl.querySelector("#column-list")
  );

  if (!hasExistingGrid) {
    sectionEl.innerHTML =
      '<div id="articles-list-view" class="articles-list-view">' +
      '<div class="section-header section-header-flex">' +
      "<div>" +
      '<h2 class="section-title">記事・コラム / 特集</h2>' +
      '<p class="articles-lead-sub">ボカロシーンのトレンド深掘り分析・ボカロP特集・楽曲レビュー・対談コラム</p>' +
      "</div>" +
      "</div>" +
      '<div class="articles-toolbar">' +
      '<div id="article-category-bar" class="article-category-bar" role="tablist" aria-label="記事カテゴリ絞り込み">' +
      '<button type="button" class="article-cat-btn active" data-category="all">すべて</button>' +
      '<button type="button" class="article-cat-btn" data-category="チャート分析">チャート分析</button>' +
      '<button type="button" class="article-cat-btn" data-category="ボカロP特集">ボカロP特集</button>' +
      '<button type="button" class="article-cat-btn" data-category="楽曲レビュー">楽曲レビュー</button>' +
      '<button type="button" class="article-cat-btn" data-category="対談・コラム">対談・コラム</button>' +
      "</div>" +
      '<div class="article-search-wrap">' +
      '<input type="search" id="article-search-input" class="ranking-search-input article-search-input" placeholder="記事タイトル・タグ・キーワードで検索..." autocomplete="off" />' +
      "</div>" +
      "</div>" +
      '<div id="articles-featured-container" class="articles-featured-container"></div>' +
      '<div id="articles-grid" class="articles-grid">' +
      '<div class="loading-state">記事・コラムを読み込んでいます...</div>' +
      "</div>" +
      "</div>" +
      '<div id="article-detail-view" class="article-detail-view" style="display: none;"></div>';
  } else if (!sectionEl.querySelector("#article-detail-view") && !sectionEl.querySelector("#column-detail-view")) {
    const detailDiv = document.createElement("div");
    detailDiv.id = "article-detail-view";
    detailDiv.className = "article-detail-view";
    detailDiv.style.display = "none";
    sectionEl.appendChild(detailDiv);
  }

  return sectionEl;
}

function updatePageSeoMeta(article) {
  const descEl = document.querySelector('meta[name="description"]');
  const ogTitleEl = document.querySelector('meta[property="og:title"]');
  const ogDescEl = document.querySelector('meta[property="og:description"]');
  const ogUrlEl = document.querySelector('meta[property="og:url"]');
  const canonicalEl = document.querySelector('link[rel="canonical"]');

  if (article && article.title) {
    const fullTitle = article.title + " | 週刊VOCALOID™複合ランキング";
    const desc =
      article.summary ||
      article.title + " - 週刊VOCALOID™複合ランキング（" + (article.category || "コラム") + "）";
    const articleUrl =
      OFFICIAL_SITE_URL + "/articles/" + encodeURIComponent(article.id) + ".html";

    document.title = fullTitle;
    if (descEl) descEl.setAttribute("content", desc);
    if (ogTitleEl) ogTitleEl.setAttribute("content", fullTitle);
    if (ogDescEl) ogDescEl.setAttribute("content", desc);
    if (ogUrlEl) ogUrlEl.setAttribute("content", articleUrl);
    if (canonicalEl) canonicalEl.setAttribute("href", articleUrl);
  } else {
    document.title = DEFAULT_PAGE_TITLE;
    if (descEl && DEFAULT_META_DESC) descEl.setAttribute("content", DEFAULT_META_DESC);
    if (ogTitleEl) ogTitleEl.setAttribute("content", DEFAULT_PAGE_TITLE);
    if (ogDescEl && DEFAULT_META_DESC) ogDescEl.setAttribute("content", DEFAULT_META_DESC);
    if (ogUrlEl) ogUrlEl.setAttribute("content", OFFICIAL_SITE_URL);
    if (canonicalEl) canonicalEl.setAttribute("href", OFFICIAL_SITE_URL);
  }
}

async function ensureArticlesLoaded() {
  if (state.articlesDataLoaded) return;
  if (state.articlesLoadingPromise) return state.articlesLoadingPromise;
  state.articlesLoadingPromise = loadArticlesData().finally(function () {
    state.articlesDataLoaded = true;
    state.articlesLoadingPromise = null;
  });
  return state.articlesLoadingPromise;
}

async function initArticlesSystem() {
  const sectionEl = ensureArticlesTabStructure();
  if (!sectionEl) return;

  const articlesTabId = getArticlesTabId();
  const tabBtn = document.querySelector('.tab-btn[data-tab="' + articlesTabId + '"]');
  if (tabBtn) {
    // 初期表示を重くしないため、「記事・コラム」タブにマウスを乗せた時またはクリックした時に初めて通信を行う
    tabBtn.addEventListener(
      "mouseenter",
      function () {
        if (!isDataSaverEnabled()) ensureArticlesLoaded();
      },
      { passive: true }
    );
    tabBtn.addEventListener("click", function () {
      ensureArticlesLoaded();
    });
  }

  sectionEl.addEventListener("click", function (e) {
    const catBtn = e.target.closest(
      ".article-cat-btn, .category-pill, .column-cat-btn, [data-category]"
    );
    if (catBtn && catBtn.hasAttribute("data-category")) {
      const cat = catBtn.getAttribute("data-category") || "all";
      state.currentArticleCategory = cat;
      sectionEl
        .querySelectorAll(".article-cat-btn, .category-pill, .column-cat-btn, [data-category]")
        .forEach(function (b) {
          b.classList.toggle("active", b.getAttribute("data-category") === cat);
        });
      if (state.currentOpenArticleId) {
        closeArticleDetail(false);
      }
      renderArticlesView();
      return;
    }

    // 個別URLリンク (<a class="article-seo-link" href="./articles/xxx.html">) が通常クリックされた場合はそのまま個別URLへ遷移させても良いし、
    // Ctrl/Cmdクリック時はブラウザ標準の別タブ遷移に任せる
    const seoLink = e.target.closest(".article-seo-link");
    if (seoLink) {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) {
        return;
      }
      // プレビュー環境(localhost)では未ビルドの下書きも読めるようSPAリーダーで開く
      if (isLocalOwnerPreview()) {
        e.preventDefault();
        const card = seoLink.closest("[data-article-id]");
        if (card) openArticleById(card.getAttribute("data-article-id"), true);
      }
      return;
    }

    const openCard = e.target.closest("[data-article-id]");
    if (openCard && !e.target.closest("a") && !e.target.closest("button")) {
      const aid = openCard.getAttribute("data-article-id");
      if (aid) {
        if (!isLocalOwnerPreview()) {
          window.location.href = "./articles/" + encodeURIComponent(aid) + ".html";
        } else {
          openArticleById(aid, true);
        }
      }
      return;
    }

    const backBtn = e.target.closest("#article-back-btn, #column-back-btn, .article-back-btn");
    if (backBtn) {
      closeArticleDetail(true);
      return;
    }

    const shareArticleBtn = e.target.closest(".share-article-x-btn");
    if (shareArticleBtn) {
      const aid = shareArticleBtn.getAttribute("data-share-id");
      const title = shareArticleBtn.getAttribute("data-share-title");
      const cat = shareArticleBtn.getAttribute("data-share-cat") || "記事・コラム";
      const shareUrl = OFFICIAL_SITE_URL + "/articles/" + encodeURIComponent(aid) + ".html";
      const text =
        "【" +
        cat +
        "】" +
        title +
        "\n｜週刊VOCALOID™複合ランキング\n#週刊VOCALOID複合ランキング #ボカロ";
      const intentUrl =
        "https://twitter.com/intent/tweet?text=" +
        encodeURIComponent(text) +
        "&url=" +
        encodeURIComponent(shareUrl);
      window.open(intentUrl, "_blank", "noopener,noreferrer");
      return;
    }

    const copyArticleUrlBtn = e.target.closest(".copy-article-url-btn");
    if (copyArticleUrlBtn) {
      const aid = copyArticleUrlBtn.getAttribute("data-share-id");
      const shareUrl = OFFICIAL_SITE_URL + "/articles/" + encodeURIComponent(aid) + ".html";
      navigator.clipboard
        .writeText(shareUrl)
        .then(function () {
          showToast("🔗 記事の個別URLをコピーしました！");
        })
        .catch(function () {
          showToast("コピーに失敗しました");
        });
    }
  });

  const searchInput =
    sectionEl.querySelector("#article-search-input") ||
    sectionEl.querySelector("#column-search-input") ||
    sectionEl.querySelector('input[type="search"]');
  if (searchInput) {
    searchInput.addEventListener("input", function (e) {
      state.currentArticleSearchQuery = (e.target.value || "").trim().toLowerCase();
      if (state.currentOpenArticleId) {
        closeArticleDetail(false);
      }
      renderArticlesView();
    });
  }

  // 初回アクセス時にURLハッシュが #article= または #tab-articles の場合のみ即時読み込みし、
  // 通常のトップページ表示時はバックグラウンドアイドル時まで待機して初期表示を高速化する
  const initialHash = window.location.hash || "";
  if (
    initialHash.indexOf("#article=") === 0 ||
    initialHash === "#" + articlesTabId ||
    sectionEl.classList.contains("active")
  ) {
    await ensureArticlesLoaded();
    checkAndHandleArticleHash();
  } else if (!isSmartphoneViewport() && !isDataSaverEnabled()) {
    const idleFn =
      window.requestIdleCallback ||
      function (cb) {
        setTimeout(cb, 2800);
      };
    idleFn(function () {
      ensureArticlesLoaded();
    });
  }

  window.addEventListener("hashchange", function () {
    ensureArticlesLoaded().then(checkAndHandleArticleHash);
  });
}

async function loadArticlesData() {
  // 本番環境では本文(body)を含まない超軽量な articles_index.json を最優先で読み込む
  const candidateUrls = isLocalOwnerPreview()
    ? [
        "./data/articles/articles_master.json",
        "./data/articles_index.json",
        "./data/articles.json",
        "public/data/articles_index.json",
        "public/data/articles.json"
      ]
    : [
        "./data/articles_index.json",
        "data/articles_index.json",
        "public/data/articles_index.json",
        "./data/articles.json",
        "data/articles.json",
        "public/data/articles.json"
      ];

  const rawData = await fetchJsonWithFallback(candidateUrls, "no-cache");
  let list = [];
  if (Array.isArray(rawData)) {
    list = rawData;
  } else if (rawData && Array.isArray(rawData.articles)) {
    list = rawData.articles;
  }

  state.allArticlesData = list.filter(function (a) {
    return isArticleReleasedForPublic(a);
  });

  state.allArticlesData.sort(function (a, b) {
    const da = String(a.publishedAt || a.publishAt || a.updatedAt || "");
    const db = String(b.publishedAt || b.publishAt || b.updatedAt || "");
    return db.localeCompare(da);
  });

  renderArticlesView();
}

function checkAndHandleArticleHash() {
  const hash = window.location.hash || "";
  if (hash.indexOf("#article=") === 0) {
    const targetId = decodeURIComponent(hash.replace("#article=", "").trim());
    if (targetId) {
      const tabId = getArticlesTabId();
      activateTabById(tabId);
      openArticleById(targetId, false);
    }
  } else if (hash === "#" + getArticlesTabId()) {
    activateTabById(getArticlesTabId());
    if (state.currentOpenArticleId) closeArticleDetail(false);
  } else if (state.currentOpenArticleId) {
    closeArticleDetail(false);
  }
}

function resolveArticleThumbnail(article) {
  if (!article) return "";
  if (article.thumbnail) {
    const safeUrl = sanitizeSafeImageUrl(article.thumbnail);
    if (safeUrl) return safeUrl;
  }
  if (article.youtubeId || article.youtube_id) {
    const yid = sanitizeYoutubeId(article.youtubeId || article.youtube_id);
    if (yid) return "https://i.ytimg.com/vi/" + yid + "/hqdefault.jpg";
  }
  return "";
}

function formatArticleDate(article) {
  const raw = article.publishedAt || article.publishAt || article.updatedAt || "";
  const m = String(raw).match(/(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
  if (m) {
    return m[1] + "." + String(m[2]).padStart(2, "0") + "." + String(m[3]).padStart(2, "0");
  }
  return raw || "";
}

function getFilteredArticles() {
  return state.allArticlesData.filter(function (a) {
    if (state.currentArticleCategory !== "all") {
      if ((a.category || "") !== state.currentArticleCategory) return false;
    }
    if (state.currentArticleSearchQuery) {
      const tagsStr = Array.isArray(a.tags) ? a.tags.join(" ") : String(a.tags || "");
      const hay = (
        (a.title || "") +
        " " +
        (a.summary || "") +
        " " +
        (a.category || "") +
        " " +
        tagsStr +
        " " +
        (a.author || "")
      ).toLowerCase();
      if (hay.indexOf(state.currentArticleSearchQuery) === -1) return false;
    }
    return true;
  });
}

function buildArticleTagRowHtml(tags) {
  if (!Array.isArray(tags) || !tags.length) return "";
  const spans = tags.map(function (t) {
    return '<span class="article-tag">#' + escapeHtml(t) + "</span>";
  });
  return '<div class="article-tag-row">' + spans.join("") + "</div>";
}

function getArticlePermalink(article) {
  const cleanId = encodeURIComponent(String(article.id || "").trim());
  return "./articles/" + cleanId + ".html";
}

function buildHeroArticleHtml(heroArticle) {
  const thumbUrl = resolveArticleThumbnail(heroArticle);
  const dateStr = formatArticleDate(heroArticle);
  const tags = Array.isArray(heroArticle.tags) ? heroArticle.tags : [];
  const permalink = getArticlePermalink(heroArticle);

  const thumbInner = thumbUrl
    ? '<img src="' +
      escapeHtml(thumbUrl) +
      '" alt="' +
      escapeHtml(heroArticle.title) +
      '" class="article-hero-thumb" loading="lazy" decoding="async" referrerpolicy="no-referrer" />'
    : '<div class="article-thumb-placeholder"><span>VOCALOID COLUMN</span></div>';

  const authorHtml = heroArticle.author
    ? '<span class="article-author">by ' + escapeHtml(heroArticle.author) + "</span>"
    : "";

  return (
    '<article class="article-hero-card" data-article-id="' +
    escapeHtml(heroArticle.id) +
    '">' +
    '<div class="article-hero-thumb-wrap">' +
    thumbInner +
    '<span class="article-pickup-ribbon">PICK UP 特集</span>' +
    "</div>" +
    '<div class="article-hero-body">' +
    '<div class="article-card-meta">' +
    '<span class="article-cat-badge">' +
    escapeHtml(heroArticle.category || "コラム") +
    "</span>" +
    '<time class="article-date">' +
    escapeHtml(dateStr) +
    "</time>" +
    authorHtml +
    "</div>" +
    '<h3 class="article-hero-title"><a href="' +
    escapeHtml(permalink) +
    '" class="article-seo-link" style="color:inherit;text-decoration:none;">' +
    escapeHtml(heroArticle.title) +
    "</a></h3>" +
    '<p class="article-hero-summary">' +
    escapeHtml(heroArticle.summary || "") +
    "</p>" +
    buildArticleTagRowHtml(tags) +
    '<a href="' +
    escapeHtml(permalink) +
    '" class="article-read-more article-seo-link" style="text-decoration:none;">記事を読む ➔</a>' +
    "</div>" +
    "</article>"
  );
}

function buildGridArticleCardHtml(art) {
  const thumbUrl = resolveArticleThumbnail(art);
  const dateStr = formatArticleDate(art);
  const tags = Array.isArray(art.tags) ? art.tags.slice(0, 4) : [];
  const permalink = getArticlePermalink(art);

  const thumbInner = thumbUrl
    ? '<img src="' +
      escapeHtml(thumbUrl) +
      '" alt="' +
      escapeHtml(art.title) +
      '" class="article-card-thumb" loading="lazy" decoding="async" referrerpolicy="no-referrer" />'
    : '<div class="article-thumb-placeholder"><span>COLUMN</span></div>';

  const authorHtml = art.author
    ? '<span class="article-author">' + escapeHtml(art.author) + "</span>"
    : "";

  return (
    '<article class="article-card" data-article-id="' +
    escapeHtml(art.id) +
    '">' +
    '<div class="article-card-thumb-wrap">' +
    thumbInner +
    '<span class="article-cat-badge overlay-badge">' +
    escapeHtml(art.category || "コラム") +
    "</span>" +
    "</div>" +
    '<div class="article-card-body">' +
    '<div class="article-card-meta">' +
    '<time class="article-date">' +
    escapeHtml(dateStr) +
    "</time>" +
    authorHtml +
    "</div>" +
    '<h3 class="article-card-title"><a href="' +
    escapeHtml(permalink) +
    '" class="article-seo-link" style="color:inherit;text-decoration:none;">' +
    escapeHtml(art.title) +
    "</a></h3>" +
    '<p class="article-card-summary">' +
    escapeHtml(art.summary || "") +
    "</p>" +
    buildArticleTagRowHtml(tags) +
    "</div>" +
    "</article>"
  );
}

function renderArticlesView() {
  const sectionEl = document.getElementById(getArticlesTabId());
  if (!sectionEl) return;

  const featuredContainer =
    sectionEl.querySelector("#articles-featured-container") ||
    sectionEl.querySelector("#column-featured-container") ||
    sectionEl.querySelector("#articles-featured");
  const gridContainer =
    sectionEl.querySelector("#articles-grid") ||
    sectionEl.querySelector("#column-grid") ||
    sectionEl.querySelector("#articles-container") ||
    sectionEl.querySelector("#column-list");

  const emptyStateEl =
    sectionEl.querySelector("#column-empty-state") ||
    sectionEl.querySelector("#articles-empty-state");

  if (!gridContainer) return;

  if (!state.allArticlesData.length) {
    if (featuredContainer) featuredContainer.innerHTML = "";
    if (emptyStateEl) {
      emptyStateEl.style.display = "block";
      gridContainer.innerHTML = "";
    } else {
      gridContainer.innerHTML =
        '<div class="articles-empty-card">' +
        '<div class="articles-empty-badge">COMING SOON</div>' +
        '<h3 class="articles-empty-title">記事・コラムは現在準備中です</h3>' +
        '<p class="articles-empty-desc">' +
        "このタブでは、週間チャートの深掘りトレンド考察、注目ボカロP・新曲の特集レビュー、対話形式のコラム記事を不定期で公開していきます。<br>" +
        "第1弾の記事公開まで今しばらくお待ちください！" +
        "</p>" +
        "</div>";
    }
    return;
  }

  if (emptyStateEl) {
    emptyStateEl.style.display = "none";
  }

  const filtered = getFilteredArticles();
  if (!filtered.length) {
    if (featuredContainer) featuredContainer.innerHTML = "";
    gridContainer.innerHTML =
      '<div class="empty-state">条件に一致する記事・コラムが見つかりませんでした。</div>';
    return;
  }

  const showHero = state.currentArticleCategory === "all" && !state.currentArticleSearchQuery;
  const heroArticle = showHero
    ? filtered.find(function (a) {
        return Boolean(a.featured);
      }) || filtered[0]
    : null;

  const gridList =
    heroArticle && featuredContainer
      ? filtered.filter(function (a) {
          return a.id !== heroArticle.id;
        })
      : filtered;

  if (featuredContainer) {
    featuredContainer.innerHTML = heroArticle ? buildHeroArticleHtml(heroArticle) : "";
  }

  if (!gridList.length && heroArticle && featuredContainer) {
    gridContainer.innerHTML = "";
    return;
  }

  gridContainer.innerHTML = gridList.map(buildGridArticleCardHtml).join("");
}

async function openArticleById(articleId, updateHash) {
  await ensureArticlesLoaded();
  let article = state.allArticlesData.find(function (a) {
    return String(a.id) === String(articleId);
  });
  if (!article) {
    showToast("指定された記事が見つかりません");
    return;
  }

  // 軽量インデックス(articles_index.json)から読み込まれていて本文(body)が未取得の場合、オンデマンドで個別記事JSONを取得
  if (!article.body && !article.content) {
    const cleanId = encodeURIComponent(String(article.id).trim());
    const fullArticle = await fetchJsonWithFallback(
      [
        "./data/articles/" + cleanId + ".json",
        "public/data/articles/" + cleanId + ".json",
        "./data/articles.json"
      ],
      "default"
    );
    if (fullArticle) {
      if (Array.isArray(fullArticle.articles)) {
        const found = fullArticle.articles.find(function (x) {
          return String(x.id) === String(articleId);
        });
        if (found) Object.assign(article, found);
      } else if (fullArticle.body || fullArticle.content) {
        Object.assign(article, fullArticle);
      }
    }
  }

  state.currentOpenArticleId = article.id;
  if (updateHash) {
    history.pushState(null, "", "#article=" + encodeURIComponent(article.id));
  }
  updatePageSeoMeta(article);

  const sectionEl = document.getElementById(getArticlesTabId());
  if (!sectionEl) return;

  const listView =
    sectionEl.querySelector("#articles-list-view") ||
    sectionEl.querySelector("#column-list-view");
  const detailView =
    sectionEl.querySelector("#article-detail-view") ||
    sectionEl.querySelector("#column-detail-view");
  if (!detailView) return;

  if (listView) {
    listView.style.display = "none";
  } else {
    Array.from(sectionEl.children).forEach(function (ch) {
      if (ch !== detailView) ch.style.display = "none";
    });
  }

  const thumbUrl = resolveArticleThumbnail(article);
  const dateStr = formatArticleDate(article);
  const tags = Array.isArray(article.tags) ? article.tags : [];
  const bodyHtml = parseArticleBodyHtml(article.body || article.content || "");
  const related = state.allArticlesData
    .filter(function (a) {
      return a.id !== article.id;
    })
    .slice(0, 3);

  const authorHtml = article.author
    ? '<span class="article-author">執筆: ' + escapeHtml(article.author) + "</span>"
    : "";

  const heroImgHtml = thumbUrl
    ? '<div class="article-reader-hero-img-wrap"><img src="' +
      escapeHtml(thumbUrl) +
      '" alt="' +
      escapeHtml(article.title) +
      '" class="article-reader-hero-img" referrerpolicy="no-referrer" /></div>'
    : "";

  const leadHtml = article.summary
    ? '<div class="article-reader-lead">' +
      escapeHtml(article.summary).replace(/\n/g, "<br>") +
      "</div>"
    : "";

  let relatedHtml = "";
  if (related.length) {
    const relatedCards = related.map(buildGridArticleCardHtml).join("");
    relatedHtml =
      '<div class="article-related-section">' +
      '<h3 class="section-title">その他の記事・コラム</h3>' +
      '<div class="articles-grid related-grid">' +
      relatedCards +
      "</div>" +
      "</div>";
  }

  detailView.style.display = "block";
  detailView.innerHTML =
    '<div class="article-reader-card">' +
    '<div class="article-reader-topbar">' +
    '<button type="button" id="article-back-btn" class="article-back-btn">← 記事一覧へ戻る</button>' +
    '<div class="article-share-actions">' +
    '<button type="button" class="action-btn share-article-x-btn" data-share-id="' +
    escapeHtml(article.id) +
    '" data-share-title="' +
    escapeHtml(article.title) +
    '" data-share-cat="' +
    escapeHtml(article.category || "記事・コラム") +
    '">𝕏 記事をシェア</button>' +
    '<button type="button" class="action-btn copy-article-url-btn" data-share-id="' +
    escapeHtml(article.id) +
    '">🔗 個別URLをコピー</button>' +
    "</div>" +
    "</div>" +
    '<header class="article-reader-header">' +
    '<div class="article-card-meta">' +
    '<span class="article-cat-badge">' +
    escapeHtml(article.category || "コラム") +
    "</span>" +
    '<time class="article-date">公開: ' +
    escapeHtml(dateStr) +
    "</time>" +
    authorHtml +
    "</div>" +
    '<h1 class="article-reader-title">' +
    escapeHtml(article.title) +
    "</h1>" +
    buildArticleTagRowHtml(tags) +
    "</header>" +
    heroImgHtml +
    leadHtml +
    '<div class="article-reader-content">' +
    bodyHtml +
    "</div>" +
    '<footer class="article-reader-footer">' +
    '<div class="article-share-box">' +
    "<span>この記事をシェアする：</span>" +
    '<div class="article-share-actions">' +
    '<button type="button" class="action-btn share-article-x-btn" data-share-id="' +
    escapeHtml(article.id) +
    '" data-share-title="' +
    escapeHtml(article.title) +
    '" data-share-cat="' +
    escapeHtml(article.category || "記事・コラム") +
    '">𝕏 ポストする</button>' +
    '<button type="button" class="action-btn copy-article-url-btn" data-share-id="' +
    escapeHtml(article.id) +
    '">🔗 個別URLをコピー</button>' +
    "</div>" +
    "</div>" +
    '<button type="button" class="article-back-btn bottom-back-btn">← 記事・コラム一覧へ戻る</button>' +
    "</footer>" +
    "</div>" +
    relatedHtml;

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeArticleDetail(clearHash) {
  state.currentOpenArticleId = null;
  updatePageSeoMeta(null);
  if (clearHash && window.location.hash.indexOf("#article=") === 0) {
    history.pushState(null, "", window.location.pathname + window.location.search);
  }
  const sectionEl = document.getElementById(getArticlesTabId());
  if (!sectionEl) return;

  const listView =
    sectionEl.querySelector("#articles-list-view") ||
    sectionEl.querySelector("#column-list-view");
  const detailView =
    sectionEl.querySelector("#article-detail-view") ||
    sectionEl.querySelector("#column-detail-view");
  if (detailView) detailView.style.display = "none";

  if (listView) {
    listView.style.display = "block";
  } else {
    Array.from(sectionEl.children).forEach(function (ch) {
      if (ch !== detailView) ch.style.display = "";
    });
  }
}
