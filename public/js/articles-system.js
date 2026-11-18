/**
 * 記事・コラムシステム制御（タブDOM初期化・遅延読み込み・イベント委譲・URLハッシュ連携）モジュール
 */
import { OFFICIAL_SITE_URL, state } from "./config-state.js";
import {
  isSmartphoneViewport,
  isDataSaverEnabled,
  isLocalOwnerPreview,
  isArticleReleasedForPublic
} from "./utils.js";
import { fetchJsonWithFallback } from "./api.js";
import { showToast } from "./ui-common.js";
import {
  getArticlesTabId,
  renderArticlesView,
  openArticleById,
  closeArticleDetail
} from "./article-renderer.js";

let onTabActivateCallback = null;

function invokeTabActivate(tabId, explicitFn) {
  const fn = typeof explicitFn === "function" ? explicitFn : onTabActivateCallback;
  if (typeof fn === "function") {
    fn(tabId);
  }
}

/** 記事・コラムタブのセクションDOMが存在しない場合にフォールバック構造を自動生成する */
export function ensureArticlesTabStructure(onTabActivate) {
  if (typeof onTabActivate === "function") {
    onTabActivateCallback = onTabActivate;
  }
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
        invokeTabActivate(tabId);
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
      '<div class="section-header section-header-flex"><div>' +
      '<h2 class="section-title">記事・コラム / 特集</h2>' +
      '<p class="articles-lead-sub">ボカロシーンのトレンド深掘り分析・ボカロP特集・楽曲レビュー・対談コラム</p>' +
      "</div></div>" +
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
      "</div></div>" +
      '<div id="articles-featured-container" class="articles-featured-container"></div>' +
      '<div id="articles-grid" class="articles-grid">' +
      '<div class="loading-state">記事・コラムを読み込んでいます...</div>' +
      "</div></div>" +
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

/** 記事一覧インデックスがまだ読み込まれていない場合のみ1回だけ取得する */
export async function ensureArticlesLoaded() {
  if (state.articlesDataLoaded) return;
  if (state.articlesLoadingPromise) return state.articlesLoadingPromise;
  state.articlesLoadingPromise = loadArticlesData().finally(function () {
    state.articlesDataLoaded = true;
    state.articlesLoadingPromise = null;
  });
  return state.articlesLoadingPromise;
}

/** 記事・コラムシステムのイベントリスナー登録、遅延ロード、URLハッシュ制御を初期化する */
export async function initArticlesSystem(onTabActivate) {
  if (typeof onTabActivate === "function") {
    onTabActivateCallback = onTabActivate;
  }
  const sectionEl = ensureArticlesTabStructure(onTabActivateCallback);
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
    const catBtn = e.target.closest(".article-cat-btn, .category-pill, .column-cat-btn, [data-category]");
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
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
      // プレビュー環境(localhost)では未ビルドの下書きも読めるようSPAリーダーで開く
      if (isLocalOwnerPreview()) {
        e.preventDefault();
        const card = seoLink.closest("[data-article-id]");
        if (card) openArticleById(card.getAttribute("data-article-id"), true, ensureArticlesLoaded);
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
          openArticleById(aid, true, ensureArticlesLoaded);
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
        "【" + cat + "】" + title +
        "\n｜週刊VOCALOID™複合ランキング\n#週刊VOCALOID複合ランキング #ボカロ";
      const intentUrl =
        "https://twitter.com/intent/tweet?text=" + encodeURIComponent(text) +
        "&url=" + encodeURIComponent(shareUrl);
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
    ensureArticlesLoaded().then(function () {
      checkAndHandleArticleHash();
    });
  });
}

/** 記事インデックスJSONを取得し、公開記事を降順ソートして一覧描画する */
export async function loadArticlesData() {
  // 本番環境では本文(body)を含まない超軽量な articles_index.json を最優先で読み込む
  const candidateUrls = isLocalOwnerPreview()
    ? ["./data/articles/articles_master.json", "./data/articles_index.json", "./data/articles.json", "public/data/articles_index.json", "public/data/articles.json"]
    : ["./data/articles_index.json", "data/articles_index.json", "public/data/articles_index.json", "./data/articles.json", "data/articles.json", "public/data/articles.json"];

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

/** URLハッシュ (#article= / #tab-articles 等) に応じて記事タブおよび個別記事を開閉する */
export function checkAndHandleArticleHash(onTabActivate) {
  const hash = window.location.hash || "";
  if (hash.indexOf("#article=") === 0) {
    const targetId = decodeURIComponent(hash.replace("#article=", "").trim());
    if (targetId) {
      const tabId = getArticlesTabId();
      invokeTabActivate(tabId, onTabActivate);
      openArticleById(targetId, false, ensureArticlesLoaded);
    }
  } else if (hash === "#" + getArticlesTabId()) {
    invokeTabActivate(getArticlesTabId(), onTabActivate);
    if (state.currentOpenArticleId) closeArticleDetail(false);
  } else if (state.currentOpenArticleId) {
    closeArticleDetail(false);
  }
}
