/**
 * ランキングインサイト・解説タブ描画およびポイント計算モジュール
 */
import { WEIGHTS, METRIC_COLORS, state } from "./config-state.js";
import { escapeHtml, isSmartphoneViewport } from "./utils.js";

const INSIGHT_METRICS = [
  { key: "yt_views", label: "YouTube 再生", cssClass: "seg-yt-views", color: METRIC_COLORS.yt_views },
  { key: "yt_likes", label: "YouTube 高評価", cssClass: "seg-yt-likes", color: METRIC_COLORS.yt_likes },
  { key: "yt_comments", label: "YouTube コメント", cssClass: "seg-yt-comments", color: METRIC_COLORS.yt_comments },
  { key: "nc_views", label: "ニコ動 再生", cssClass: "seg-nc-views", color: METRIC_COLORS.nc_views },
  { key: "nc_mylists", label: "ニコ動 マイリス", cssClass: "seg-nc-mylists", color: METRIC_COLORS.nc_mylists },
  { key: "nc_comments", label: "ニコ動 コメント", cssClass: "seg-nc-comments", color: METRIC_COLORS.nc_comments }
];

/** 楽曲の6指標獲得ポイントと合算内訳を算出する */
export function getPointsBreakdown(song) {
  const raw = song.raw || {};
  const pts = song.pts || {};

  const rawNcMylist = raw.nc_mylist !== undefined ? raw.nc_mylist : raw.nc_mylists || 0;
  const ptsNcMylist =
    pts.nc_mylist !== undefined
      ? pts.nc_mylist
      : pts.nc_mylists !== undefined
      ? pts.nc_mylists
      : rawNcMylist * WEIGHTS.nc_mylist;

  const yt_views = pts.yt_views !== undefined ? pts.yt_views : (raw.yt_views || 0) * WEIGHTS.yt_views;
  const yt_likes = pts.yt_likes !== undefined ? pts.yt_likes : (raw.yt_likes || 0) * WEIGHTS.yt_likes;
  const yt_comments =
    pts.yt_comments !== undefined ? pts.yt_comments : (raw.yt_comments || 0) * WEIGHTS.yt_comments;

  const nc_views = pts.nc_views !== undefined ? pts.nc_views : (raw.nc_views || 0) * WEIGHTS.nc_views;
  const nc_mylists = ptsNcMylist;
  const nc_comments =
    pts.nc_comments !== undefined ? pts.nc_comments : (raw.nc_comments || 0) * WEIGHTS.nc_comments;

  const yt_total = pts.yt_total !== undefined ? pts.yt_total : yt_views + yt_likes + yt_comments;
  const nc_total = pts.nc_total !== undefined ? pts.nc_total : nc_views + nc_mylists + nc_comments;
  const calcSum = yt_total + nc_total;
  const total_pt = song.total_pt !== undefined && song.total_pt > 0 ? song.total_pt : calcSum;

  return {
    yt_views: yt_views,
    yt_likes: yt_likes,
    yt_comments: yt_comments,
    nc_views: nc_views,
    nc_mylists: nc_mylists,
    nc_comments: nc_comments,
    yt_total: yt_total,
    nc_total: nc_total,
    total_pt: total_pt,
    calcSum: calcSum > 0 ? calcSum : 1,
    rawNcMylist: rawNcMylist
  };
}

/** ポイント前週比バッジのHTMLを生成する */
export function formatPointRatioHTML(song) {
  let ratio = song.pt_ratio;
  if (
    (ratio === undefined || ratio === null) &&
    typeof song.prev_total_pt === "number" &&
    song.prev_total_pt > 0
  ) {
    ratio = Math.round((song.total_pt / song.prev_total_pt) * 100);
  }

  if (ratio === undefined || ratio === null || isNaN(ratio)) {
    return '<span class="pt-ratio-new">NEW</span>';
  }

  const roundedRatio = Math.round(ratio);
  const isUp =
    typeof song.prev_total_pt === "number"
      ? song.total_pt > song.prev_total_pt
      : roundedRatio > 100;
  const isDown =
    typeof song.prev_total_pt === "number"
      ? song.total_pt < song.prev_total_pt
      : roundedRatio < 100;

  if (isUp) {
    return '<span class="pt-ratio-up">∧' + roundedRatio + "%</span>";
  } else if (isDown) {
    return '<span class="pt-ratio-down">∨' + roundedRatio + "%</span>";
  } else {
    return '<span class="pt-ratio-stay">→' + roundedRatio + "%</span>";
  }
}

/** TOP 10 の6指標構成比グラフ（Chart.js または HTML フォールバック）を描画する */
export function renderTop10InsightChart(ranking) {
  const wrapper =
    document.getElementById("insight-chart-wrapper") || document.querySelector(".chart-wrapper");
  if (!wrapper) return;

  const top10 = ranking.slice(0, 10);
  if (!top10.length) return;

  const isMobile = isSmartphoneViewport();
  const labels = top10.map(function (s, i) {
    const r = parseInt(s.rank, 10) || i + 1;
    const titleStr = String(s.title || "");
    const shortTitle = isMobile && titleStr.length > 10 ? titleStr.slice(0, 10) + "…" : titleStr;
    return r + "位: " + shortTitle;
  });
  const breakdowns = top10.map(function (s) {
    return getPointsBreakdown(s);
  });

  let canvas = document.getElementById("top5Chart") || document.getElementById("top20Chart");

  if (typeof Chart !== "undefined") {
    if (!canvas) {
      wrapper.innerHTML = '<canvas id="top5Chart"></canvas>';
      canvas = document.getElementById("top5Chart");
    }

    if (state.insightChartInstance) {
      state.insightChartInstance.destroy();
      state.insightChartInstance = null;
    }

    try {
      const ctx = canvas.getContext("2d");
      state.insightChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
          labels: labels,
          datasets: INSIGHT_METRICS.map(function (m) {
            return {
              label: m.label,
              data: breakdowns.map(function (b) {
                return b[m.key];
              }),
              backgroundColor: m.color
            };
          })
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: isMobile ? 200 : 350 },
          scales: {
            x: {
              stacked: true,
              ticks: {
                color: "#94a3b8",
                font: { size: isMobile ? 10 : 12 },
                callback: function (value) {
                  if (isMobile && value >= 10000) {
                    return Math.round(value / 10000) + "万";
                  }
                  return Number(value).toLocaleString() + " pt";
                }
              },
              grid: { color: "rgba(148, 163, 184, 0.12)" }
            },
            y: {
              stacked: true,
              ticks: { color: "#f8fafc", font: { size: isMobile ? 11 : 12, weight: "600" } },
              grid: { display: false }
            }
          },
          plugins: {
            legend: {
              position: "top",
              labels: {
                color: "#e2e8f0",
                boxWidth: isMobile ? 10 : 14,
                padding: isMobile ? 8 : 14,
                font: { size: isMobile ? 11 : 12 }
              }
            },
            tooltip: {
              callbacks: {
                label: function (context) {
                  const val = Number(context.raw || 0).toLocaleString();
                  return context.dataset.label + ": " + val + " pt";
                }
              }
            }
          }
        }
      });
      state.insightChartInstance.resize();
      return;
    } catch (err) {
      console.warn("Chart.js 描画エラーのため HTML フォールバックを使用します:", err);
    }
  }

  let maxPt = 1;
  for (let i = 0; i < breakdowns.length; i++) {
    if (breakdowns[i].total_pt > maxPt) {
      maxPt = breakdowns[i].total_pt;
    }
  }

  const rowHtmls = top10.map(function (song, i) {
    const r = parseInt(song.rank, 10) || i + 1;
    const b = breakdowns[i];
    const wTotal = ((b.total_pt / maxPt) * 100).toFixed(2);
    const denom = b.calcSum;
    const segHtml = INSIGHT_METRICS.map(function (m) {
      return (
        '<div class="bar-seg ' +
        m.cssClass +
        '" style="width: ' +
        ((b[m.key] / denom) * 100).toFixed(2) +
        '%"></div>'
      );
    }).join("");

    return (
      '<div class="fallback-chart-row">' +
      '<div class="fallback-chart-label" title="' +
      escapeHtml(song.title) +
      '">' +
      r +
      "位: " +
      escapeHtml(song.title) +
      "</div>" +
      '<div class="fallback-chart-bar-track">' +
      '<div class="fallback-chart-bar-fill" style="width: ' +
      wTotal +
      '%">' +
      segHtml +
      "</div>" +
      "</div>" +
      '<div class="fallback-chart-pt">' +
      Number(b.total_pt).toLocaleString() +
      " pt</div>" +
      "</div>"
    );
  });

  const legendHtml = INSIGHT_METRICS.map(function (m) {
    return '<span><i class="legend-dot ' + m.cssClass + '"></i>' + m.label + "</span>";
  }).join("");

  wrapper.innerHTML =
    '<div class="fallback-chart-legend">' +
    legendHtml +
    "</div>" +
    '<div class="fallback-chart-rows">' +
    rowHtmls.join("") +
    "</div>";
}

/** TOP 10 プラットフォーム別・指標構成比テーブルを描画する */
export function renderInsightTable(ranking) {
  const tbody =
    document.getElementById("insight-table-body") ||
    document.querySelector("#insight-table-container tbody");
  if (!tbody) return;

  const top10 = ranking.slice(0, 10);
  if (!top10.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="loading-cell">データがありません。</td></tr>';
    return;
  }

  tbody.innerHTML = top10
    .map(function (song, i) {
      const r = parseInt(song.rank, 10) || i + 1;
      const bd = getPointsBreakdown(song);
      const ytRatio = bd.total_pt > 0 ? ((bd.yt_total / bd.total_pt) * 100).toFixed(1) : "0.0";
      const ncRatio = bd.total_pt > 0 ? ((bd.nc_total / bd.total_pt) * 100).toFixed(1) : "0.0";
      const chartInCount = parseInt(song.chart_in_count, 10) || 1;

      return (
        "<tr>" +
        '<td class="col-rank">' + r + "位</td>" +
        '<td class="col-song">' +
        '<span class="insight-song-title">' + escapeHtml(song.title) + "</span>" +
        '<span class="insight-song-producer">(' + escapeHtml(song.producer) + ")</span>" +
        "</td>" +
        '<td class="col-total-pt">' + Number(bd.total_pt).toLocaleString() + " pt</td>" +
        '<td class="col-pt-ratio">' + formatPointRatioHTML(song) + "</td>" +
        '<td class="col-chart-in">' + chartInCount + "回</td>" +
        '<td class="col-yt-ratio">' + ytRatio + "% (" + Number(bd.yt_total).toLocaleString() + " pt)</td>" +
        '<td class="col-nc-ratio">' + ncRatio + "% (" + Number(bd.nc_total).toLocaleString() + " pt)</td>" +
        "</tr>"
      );
    })
    .join("");
}

/** 今週のトレンド総評およびピックアップ上位楽曲解説を描画する */
export function renderCommentaryView(data, ranking) {
  const overallEl =
    document.getElementById("overall-commentary") ||
    document.getElementById("weekly-summary-text");
  if (overallEl) {
    const overallText =
      data.overall_commentary || data.weeklySummary || data.trend_analysis || "";
    overallEl.innerHTML = overallText
      ? "<p>" + escapeHtml(overallText).replace(/\n/g, "<br>") + "</p>"
      : '<p class="muted-text">今週の全体総評はまだ登録されていません。</p>';
  }

  const listEl = document.getElementById("commentary-container");
  if (!listEl) return;

  const commentedSongs = ranking.filter(function (s) {
    return s.commentary && String(s.commentary).trim() !== "";
  });
  if (!commentedSongs.length) {
    listEl.innerHTML = '<div class="empty-state">楽曲別の解説はまだ登録されていません。</div>';
    return;
  }

  listEl.innerHTML = commentedSongs
    .map(function (song, i) {
      const r = parseInt(song.rank, 10) || i + 1;
      return (
        '<div class="commentary-card">' +
        '<div class="commentary-card-header">' +
        '<span class="commentary-rank-badge">' + r + "位</span>" +
        '<h3 class="commentary-song-title">' +
        escapeHtml(song.title) +
        " <small>/ " + escapeHtml(song.producer) + "</small></h3>" +
        '<span class="commentary-song-pt">' + Number(song.total_pt || 0).toLocaleString() + " pt</span>" +
        "</div>" +
        '<div class="commentary-card-body">' +
        escapeHtml(song.commentary).replace(/\n/g, "<br>") +
        "</div>" +
        "</div>"
      );
    })
    .join("");
}
