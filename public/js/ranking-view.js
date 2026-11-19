/**
 * 週間ランキング TOP 20 カード一覧描画・フィルタ/ソート・詳細開閉・イベント委譲モジュール
 */
import { OFFICIAL_SITE_URL, state } from "./config-state.js";
import {
  escapeHtml,
  isSmartphoneViewport,
  sanitizeYoutubeId,
  sanitizeNiconicoId,
  sanitizeThumbnailUrl,
  getPrimarySongKey
} from "./utils.js";
import { getPointsBreakdown, formatPointRatioHTML } from "./insight-view.js";
import { isSongFavorited, toggleFavoriteSong } from "./favorites-toolbar.js";

const BAR_METRICS = [
  { key: "yt_views", cssClass: "seg-yt-views", label: "YouTube再生" },
  { key: "yt_likes", cssClass: "seg-yt-likes", label: "YouTube高評価" },
  { key: "yt_comments", cssClass: "seg-yt-comments", label: "YouTubeコメント" },
  { key: "nc_views", cssClass: "seg-nc-views", label: "ニコ動再生" },
  { key: "nc_mylists", cssClass: "seg-nc-mylists", label: "ニコ動マイリス" },
  { key: "nc_comments", cssClass: "seg-nc-comments", label: "ニコ動コメント" }
];

function buildMetricListItemHtml(cssClass, label, rawVal, ptVal) {
  return (
    '<li><span><i class="legend-dot ' + cssClass + '"></i>' + label + ":</span> <strong>+" +
    Number(rawVal || 0).toLocaleString() + "</strong> (" + Number(ptVal).toLocaleString() + " pt)</li>"
  );
}

/** ランキング一覧コンテナのクリックイベント委譲（詳細開閉・お気に入り・Xシェア）を初期化する */
export function initRankingEventDelegation() {
  const container = document.getElementById("ranking-container");
  if (!container) return;

  container.addEventListener("click", function (e) {
    const detailBtn = e.target.closest(".detail-toggle-btn");
    if (detailBtn) {
      e.stopPropagation();
      const rank = parseInt(detailBtn.getAttribute("data-rank"), 10);
      if (!isNaN(rank)) {
        toggleRankDetail(rank);
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
        "『" + title + "』(" + producer + ") が「週刊VOCALOID™複合ランキング」で今週 " +
        rank + "位 (" + pt + " pt) にランクイン！\n#週刊VOCALOID複合ランキング #ボカロ";
      const shareUrl =
        "https://twitter.com/intent/tweet?text=" +
        encodeURIComponent(text) +
        "&url=" +
        encodeURIComponent(OFFICIAL_SITE_URL);
      window.open(shareUrl, "_blank", "noopener,noreferrer");
    }
  });
}

/** 前週順位との変動バッジHTMLを生成する */
export function formatRankDiffBadge(song) {
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

/** ファーストビュー位置に応じたサムネイル読み込み属性を返す */
export function getOptimizedThumbnailAttrs(song, index) {
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

/** 検索・お気に入りフィルタおよび選択中のソートモードに従ってTOP20を整形する */
export function getFilteredAndSortedSongs(ranking) {
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

/** 1曲分のランキングカードおよび詳細パネルHTMLを構築する */
export function buildRankCardHtml(song, idx) {
  const rankNum = song._origRank || parseInt(song.rank, 10) || idx + 1;
  const bd = getPointsBreakdown(song);
  const raw = song.raw || {};
  const denom = bd.calcSum;

  const barSegmentsHtml = BAR_METRICS.map(function (m) {
    const pct = ((bd[m.key] / denom) * 100).toFixed(2);
    return (
      '<div class="bar-seg ' + m.cssClass + '" style="width: ' + pct + '%" title="' +
      m.label + ": " + Number(bd[m.key]).toLocaleString() + " pt (" + pct + '%)"></div>'
    );
  }).join("");

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
      '<img src="' + escapeHtml(thumbInfo.url) + '" alt="' + escapeHtml(song.title) +
      '" class="rank-thumb" width="112" height="63" loading="' + thumbInfo.loadingAttr +
      '" decoding="async" referrerpolicy="no-referrer" ' + thumbInfo.priorityAttr + " />" +
      "</div>";
  }

  const vocalHtml = song.vocal
    ? '<span class="song-vocal">feat. ' + escapeHtml(song.vocal) + "</span>"
    : "";

  const ytLinkHtml = safeYtId
    ? '<a href="https://www.youtube.com/watch?v=' + encodeURIComponent(safeYtId) +
      '" target="_blank" rel="noopener noreferrer" class="video-link yt-link">▶ YouTubeで視聴する</a>'
    : "";

  const ncLinkHtml = safeNcId
    ? '<a href="https://www.nicovideo.jp/watch/' + encodeURIComponent(safeNcId) +
      '" target="_blank" rel="noopener noreferrer" class="video-link nc-link">▶ ニコニコ動画で視聴する</a>'
    : "";

  const commentaryHtml = song.commentary
    ? '<div class="commentary-box"><h5>楽曲解説・チャート分析</h5><p>' +
      escapeHtml(song.commentary).replace(/\n/g, "<br>") + "</p></div>"
    : "";

  const favClass = isFav ? "favorited" : "";
  const favTitle = isFav ? "お気に入り解除" : "お気に入りに保存";
  const favSymbol = isFav ? "★" : "☆";

  return (
    '<article class="rank-card rank-' + rankNum + '" data-rank="' + rankNum + '">' +
    '<div class="rank-card-summary">' +
    '<div class="rank-number-col">' +
    '<span class="rank-number">' + rankNum + "<small>位</small></span>" +
    formatRankDiffBadge(song) +
    '<span class="chart-in-mini">' + chartInCount + "週目</span>" +
    "</div>" +
    thumbHtml +
    '<div class="rank-info-col">' +
    '<div class="song-title-row">' +
    '<h3 class="song-title">' + escapeHtml(song.title) + "</h3>" +
    '<div class="card-inline-actions">' +
    '<button type="button" class="fav-star-btn ' + favClass + '" data-song-key="' + escapeHtml(songKey) +
    '" title="' + favTitle + '" aria-label="お気に入り">' + favSymbol + "</button>" +
    '<button type="button" id="detail-btn-' + rankNum + '" class="detail-toggle-btn" data-rank="' +
    rankNum + '">詳細を見る ▾</button>' +
    "</div>" +
    "</div>" +
    '<div class="song-meta">' +
    '<span class="song-producer">' + escapeHtml(song.producer) + "</span>" +
    vocalHtml +
    "</div>" +
    '<div class="metric-stacked-bar">' + barSegmentsHtml + "</div>" +
    "</div>" +
    '<div class="rank-points-col">' +
    '<div class="total-points">' +
    '<span class="total-points-label">総合ポイント数</span>' +
    '<span class="total-points-value">' + Number(bd.total_pt).toLocaleString() + " <small>pt</small></span>" +
    "</div>" +
    '<div class="points-sub-row">' +
    "<span>前週比: " + formatPointRatioHTML(song) + "</span>" +
    '<span class="platform-split-text">YT ' + ytPercent + "% / NC " + ncPercent + "%</span>" +
    "</div>" +
    "</div>" +
    "</div>" +
    '<div id="detail-panel-' + rankNum + '" class="rank-detail-panel">' +
    '<div class="detail-grid">' +
    '<div class="detail-box yt-detail-box">' +
    "<h4>YouTube 指標内訳 (" + Number(bd.yt_total).toLocaleString() + " pt / " + ytPercent + "%)</h4>" +
    "<ul>" +
    buildMetricListItemHtml("seg-yt-views", "週間再生数", raw.yt_views, bd.yt_views) +
    buildMetricListItemHtml("seg-yt-likes", "週間高評価数", raw.yt_likes, bd.yt_likes) +
    buildMetricListItemHtml("seg-yt-comments", "週間コメント数", raw.yt_comments, bd.yt_comments) +
    "</ul>" +
    ytLinkHtml +
    "</div>" +
    '<div class="detail-box nc-detail-box">' +
    "<h4>ニコニコ動画 指標内訳 (" + Number(bd.nc_total).toLocaleString() + " pt / " + ncPercent + "%)</h4>" +
    "<ul>" +
    buildMetricListItemHtml("seg-nc-views", "週間再生数", raw.nc_views, bd.nc_views) +
    buildMetricListItemHtml("seg-nc-mylists", "週間マイリスト数", bd.rawNcMylist, bd.nc_mylists) +
    buildMetricListItemHtml("seg-nc-comments", "週間コメント数", raw.nc_comments, bd.nc_comments) +
    "</ul>" +
    ncLinkHtml +
    "</div>" +
    "</div>" +
    '<div class="detail-share-row">' +
    '<button type="button" class="share-song-x-btn" data-rank="' + rankNum + '" data-title="' +
    escapeHtml(song.title) + '" data-producer="' + escapeHtml(song.producer) + '" data-pt="' +
    Number(bd.total_pt).toLocaleString() + '">𝕏 この楽曲のランクインをシェアする</button>' +
    "</div>" +
    commentaryHtml +
    "</div>" +
    "</article>"
  );
}

/** ランキング一覧コンテナへTOP20カードを描画する */
export function renderRankingView(ranking) {
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

/** 指定順位の詳細パネルを開閉する */
export function toggleRankDetail(rank, event) {
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
}

if (typeof window !== "undefined") {
  window.toggleRankDetail = toggleRankDetail;
}
