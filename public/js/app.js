/**
 * アプリケーションエントリーポイント・メインタブ切替制御モジュール
 */
import { state } from "./config-state.js";
import { isSmartphoneViewport, isDataSaverEnabled, getSongsArray } from "./utils.js";
import { ensureChartJsLoaded } from "./api.js";
import {
  initSiteViewCounter,
  initBackToTopButton,
  initScrollHints,
  refreshAllScrollHints
} from "./ui-common.js";
import { renderTop10InsightChart } from "./insight-view.js";
import { loadFavoritesFromStorage, initUtilityToolbar } from "./favorites-toolbar.js";
import { initRankingEventDelegation, renderRankingView } from "./ranking-view.js";
import { initChartApp } from "./chart-data.js";
import { getArticlesTabId } from "./article-renderer.js";
import { initArticlesSystem } from "./articles-system.js";

window.__VOCALOID_APP_LOADED__ = true;

/** 全モジュールを初期化してアプリケーションを起動する */
export function startApp() {
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
  initArticlesSystem(activateTabById);

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

/** 指定タブIDのボタンとセクションをアクティブ化する */
export function activateTabById(targetId) {
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

/** メインタブナビゲーションのクリック制御を初期化する */
export function initTabs() {
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
