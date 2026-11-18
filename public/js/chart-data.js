/**
 * チャートデータ取得・アーカイブ切替・過去履歴補完・全体描画統括モジュール
 */
import { LAST_KNOWN_CHART_STORAGE_KEY, ARCHIVE_HISTORY_SESSION_KEY, state } from "./config-state.js";
import {
  isLocalOwnerPreview,
  isChartReleasedForPublic,
  sanitizeArchiveFilename,
  getSongsArray,
  getSongIdentityKeys,
  normalizePeriodString,
  extractUpdateDateString
} from "./utils.js";
import { ensureChartJsLoaded, fetchJsonWithFallback } from "./api.js";
import { showToast, refreshAllScrollHints } from "./ui-common.js";
import { renderRankingView } from "./ranking-view.js";
import { renderTop10InsightChart, renderInsightTable, renderCommentaryView } from "./insight-view.js";

function extractArchiveFileCandidate(item) {
  if (typeof item === "string") return item;
  return item.file || item.path || (item.archiveId ? item.archiveId + ".json" : item.id);
}

function hasMatchingSongKey(targetKeys, candidateSong) {
  const pKeys = getSongIdentityKeys(candidateSong);
  return targetKeys.some(function (k) {
    return pKeys.indexOf(k) !== -1;
  });
}

async function fetchArchiveJsonByFile(rawFile, cacheMode) {
  const cleanFile = sanitizeArchiveFilename(rawFile);
  if (!cleanFile) return null;
  return fetchJsonWithFallback(
    ["./data/archives/" + cleanFile, "public/data/archives/" + cleanFile],
    cacheMode
  );
}

/** チャートアプリケーション初期化（アーカイブ目次読込・最新データ表示・履歴補完） */
export async function initChartApp() {
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

/** アーカイブ一覧インデックスを取得し、切替プルダウンを初期化する */
export async function loadArchiveIndexOnly() {
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
      const fileVal = extractArchiveFileCandidate(item);
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
        const archiveData = await fetchArchiveJsonByFile(val, "default");
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

/** 過去アーカイブデータをオンデマンドで全件読み込み、sessionStorageへキャッシュする */
export async function ensureFullArchiveHistoryLoaded() {
  if (state.archiveHistoryLoaded || !state.cachedArchiveListMeta.length) return;
  state.archiveHistoryLoaded = true;

  try {
    const cachedRaw = sessionStorage.getItem(ARCHIVE_HISTORY_SESSION_KEY);
    if (cachedRaw) {
      const parsed = JSON.parse(cachedRaw);
      if (Array.isArray(parsed) && parsed.length > 0 && parsed.length >= state.cachedArchiveListMeta.length) {
        state.archiveHistoryCache = parsed;
        return;
      }
    }
  } catch (_) {
    // ignore sessionStorage error
  }

  const loadedArchives = [];
  for (let i = 0; i < state.cachedArchiveListMeta.length; i++) {
    const data = await fetchArchiveJsonByFile(
      extractArchiveFileCandidate(state.cachedArchiveListMeta[i]),
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

/** 過去アーカイブ履歴からチャートイン回数・前週ポイント・前週比を補完する */
export function enrichWithHistory(chartData) {
  const songs = getSongsArray(chartData);
  if (!songs.length) return;

  const getSortKey = function (c) {
    return c.archiveId || c.publishDate || c.period || c.updated_at || "";
  };
  const targetKey = getSortKey(chartData);

  const olderCharts = state.archiveHistoryCache
    .filter(function (c) {
      const p = getSortKey(c);
      return p && targetKey ? p < targetKey : false;
    })
    .sort(function (a, b) {
      const ka = getSortKey(a);
      const kb = getSortKey(b);
      return ka < kb ? -1 : ka > kb ? 1 : 0;
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
            return hasMatchingSongKey(keys, ps);
          });
        if (matched) count += 1;
      });
      song.chart_in_count = count;
    }

    if (song.prev_total_pt === undefined && prevChart) {
      const prevSong = getSongsArray(prevChart).find(function (ps) {
        return hasMatchingSongKey(keys, ps);
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

/** 未解禁データ取得時のフォールバックとして最新の公開済みアーカイブを取得する */
export async function loadLatestReleasedArchiveFallback() {
  for (let i = 0; i < state.cachedArchiveListMeta.length; i++) {
    const archiveData = await fetchArchiveJsonByFile(
      extractArchiveFileCandidate(state.cachedArchiveListMeta[i]),
      "no-cache"
    );
    if (archiveData && isChartReleasedForPublic(archiveData)) {
      return archiveData;
    }
  }
  return null;
}

/** 最新ランキングJSONを取得（失敗時はローカルキャッシュ利用）して全体を描画する */
export async function loadAndRenderChart() {
  const candidateUrls = isLocalOwnerPreview()
    ? ["./data/latest_ranking.json", "./data/drafts/weekly_draft.json", "./data/weekly_draft.json", "public/data/latest_ranking.json"]
    : ["./data/latest_ranking.json", "data/latest_ranking.json", "public/data/latest_ranking.json", "latest_ranking.json"];

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

/** 期間表示・バナー・ランキング一覧・インサイト表/グラフ・解説を一括描画する */
export function renderAllViews(data) {
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
