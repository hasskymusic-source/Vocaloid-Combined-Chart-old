/**
 * 共通UI・アクセスカウンター・マイルストーンバナー・トースト・スクロール誘導制御モジュール
 */
import {
  SITE_ANNOUNCEMENT_MESSAGE,
  COUNTER_NAMESPACE,
  COUNTER_KEY,
  MILESTONE_THRESHOLDS,
  state
} from "./config-state.js";
import { isLocalOwnerPreview, isSmartphoneViewport } from "./utils.js";

/**
 * 1. サイト累計アクセスカウンター ＆ 記念マイルストーン感謝バナーシステム
 */
export async function initSiteViewCounter() {
  const countEl = document.getElementById("view-count-value");
  const bannerEl = document.getElementById("milestone-banner");
  const bannerTextEl = document.getElementById("milestone-text");
  const closeBtn = document.getElementById("milestone-close-btn");

  if (closeBtn && bannerEl) {
    closeBtn.addEventListener("click", function () {
      bannerEl.style.display = "none";
    });
  }

  if (SITE_ANNOUNCEMENT_MESSAGE && bannerEl && bannerTextEl) {
    bannerTextEl.textContent = SITE_ANNOUNCEMENT_MESSAGE;
    bannerEl.style.display = "block";
  }

  try {
    const sessionKey = "vcc_session_counted";
    const alreadyCounted = sessionStorage.getItem(sessionKey) === "1" || isLocalOwnerPreview();
    const baseApi = "https://api.counterapi.dev/v1/" + COUNTER_NAMESPACE + "/" + COUNTER_KEY;
    const endpoint = alreadyCounted ? baseApi + "/" : baseApi + "/up";

    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timerId = controller
      ? setTimeout(function () {
          controller.abort();
        }, 3500)
      : null;

    const res = await fetch(endpoint, {
      cache: "no-store",
      signal: controller ? controller.signal : undefined
    });
    if (timerId) clearTimeout(timerId);

    if (res.ok) {
      const data = await res.json();
      const views = typeof data.count === "number" ? data.count : parseInt(data.count, 10);
      if (!isNaN(views) && views > 0) {
        sessionStorage.setItem(sessionKey, "1");
        localStorage.setItem("vcc_last_known_views", String(views));
        if (countEl) {
          countEl.textContent = Number(views).toLocaleString();
        }
        checkAndShowMilestoneBanner(views);
        return;
      }
    }
  } catch (_) {
    // 外部カウンターAPIがオフライン等の場合はローカルキャッシュへフォールバック
  }

  const fallbackViews = parseInt(localStorage.getItem("vcc_last_known_views") || "1", 10);
  if (countEl) {
    countEl.textContent = Number(fallbackViews).toLocaleString();
  }
}

/** 累計ビュー数や設定メッセージに応じてマイルストーンバナーを表示する */
export function checkAndShowMilestoneBanner(views) {
  if (SITE_ANNOUNCEMENT_MESSAGE) return;
  const bannerEl = document.getElementById("milestone-banner");
  const bannerTextEl = document.getElementById("milestone-text");
  if (!bannerEl || !bannerTextEl) return;

  if (state.currentChartData && state.currentChartData.milestone_message) {
    bannerTextEl.textContent = state.currentChartData.milestone_message;
    bannerEl.style.display = "block";
    return;
  }

  for (let i = 0; i < MILESTONE_THRESHOLDS.length; i++) {
    const threshold = MILESTONE_THRESHOLDS[i];
    if (views >= threshold && views < threshold * 1.15) {
      bannerTextEl.textContent =
        "🎉 累計 " +
        Number(threshold).toLocaleString() +
        " Views 突破ありがとうございます！これからも週刊VOCALOID™複合ランキングをよろしくお願いいたします。";
      bannerEl.style.display = "block";
      break;
    }
  }
}

/** トースト通知を一定時間表示する */
export function showToast(message) {
  const toastEl = document.getElementById("toast-notification");
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.classList.add("visible");
  clearTimeout(toastEl._hideTimer);
  toastEl._hideTimer = setTimeout(function () {
    toastEl.classList.remove("visible");
  }, 2600);
}

/**
 * ページ最上部へ戻るフローティングボタン制御
 */
export function initBackToTopButton() {
  const btn = document.getElementById("back-to-top-btn");
  if (!btn) return;

  window.addEventListener(
    "scroll",
    function () {
      btn.classList.toggle("visible", window.scrollY > 360);
    },
    { passive: true }
  );

  btn.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

/** タブ・テーブル・縦スクロール用の誘導ヒント表示を初期化する */
export function initScrollHints() {
  const tabNav = document.getElementById("tab-nav");
  const tabHint = document.getElementById("tab-scroll-hint");
  const tabWrapper = document.getElementById("tab-nav-wrapper");

  const updateTabHint = function () {
    if (!tabNav || !tabHint || !tabWrapper) return;
    const maxScroll = tabNav.scrollWidth - tabNav.clientWidth;
    const canScrollRight = maxScroll > 8 && tabNav.scrollLeft < maxScroll - 12;
    tabHint.classList.toggle("visible", canScrollRight);
    tabWrapper.classList.toggle("has-overflow-right", canScrollRight);
  };

  if (tabNav) {
    tabNav.addEventListener("scroll", updateTabHint, { passive: true });
    if (tabHint) {
      tabHint.addEventListener("click", function () {
        tabNav.scrollBy({ left: 160, behavior: "smooth" });
      });
    }
  }

  const setupTableScrollHints = function () {
    const containers = document.querySelectorAll(".table-responsive");
    containers.forEach(function (container) {
      if (!container.dataset.hintInitialized) {
        container.dataset.hintInitialized = "true";
        const badge = document.createElement("div");
        badge.className = "table-scroll-indicator";
        badge.innerHTML = "<span>⇄ スクロールして表示</span>";
        badge.addEventListener("click", function () {
          container.scrollBy({ left: 180, behavior: "smooth" });
        });
        container.parentElement.insertBefore(badge, container);

        const updateTableHint = function () {
          const maxScroll = container.scrollWidth - container.clientWidth;
          const isOverflowing = maxScroll > 8;
          const hasScrolled = container.scrollLeft > 24;
          badge.classList.toggle("visible", isOverflowing && !hasScrolled);
          container.classList.toggle("is-scrollable", isOverflowing && container.scrollLeft < maxScroll - 8);
        };

        container.addEventListener("scroll", updateTableHint, { passive: true });
        container._updateScrollHint = updateTableHint;
      }
      if (typeof container._updateScrollHint === "function") {
        container._updateScrollHint();
      }
    });
  };

  const vHint = document.getElementById("vertical-scroll-hint");
  let userHasScrolledVertically = false;

  const updateVerticalHint = function () {
    if (!vHint) return;
    if (!isSmartphoneViewport()) {
      vHint.classList.remove("visible");
      return;
    }
    const scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (window.scrollY > 80) {
      userHasScrolledVertically = true;
    }
    const shouldShow = !userHasScrolledVertically && scrollableHeight > 220 && window.scrollY <= 80;
    vHint.classList.toggle("visible", shouldShow);
  };

  if (vHint) {
    vHint.addEventListener("click", function () {
      window.scrollBy({ top: Math.round(window.innerHeight * 0.65), behavior: "smooth" });
    });
  }

  window.addEventListener("scroll", updateVerticalHint, { passive: true });
  window.addEventListener(
    "resize",
    function () {
      updateTabHint();
      setupTableScrollHints();
      updateVerticalHint();
    },
    { passive: true }
  );

  window._refreshScrollHintsInternal = function () {
    updateTabHint();
    setupTableScrollHints();
    updateVerticalHint();
  };

  setTimeout(window._refreshScrollHintsInternal, 80);
}

/** 登録済みの全スクロールヒント表示を再評価する */
export function refreshAllScrollHints() {
  if (typeof window._refreshScrollHintsInternal === "function") {
    window._refreshScrollHintsInternal();
  }
}
