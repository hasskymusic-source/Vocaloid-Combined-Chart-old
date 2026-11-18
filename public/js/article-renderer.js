/**
 * 記事・コラム一覧カード描画・個別記事リーダー表示・動的SEOメタ更新モジュール
 */
import { OFFICIAL_SITE_URL, DEFAULT_PAGE_TITLE, DEFAULT_META_DESC, state } from "./config-state.js";
import { escapeHtml, sanitizeYoutubeId, sanitizeSafeImageUrl } from "./utils.js";
import { fetchJsonWithFallback } from "./api.js";
import { showToast } from "./ui-common.js";
import { parseArticleBodyHtml } from "./article-parser.js";

function queryFirst(root, selectors) {
  for (let i = 0; i < selectors.length; i++) {
    const el = root.querySelector(selectors[i]);
    if (el) return el;
  }
  return null;
}

function setMetaAttr(selector, attr, val) {
  if (!val) return;
  const el = document.querySelector(selector);
  if (el) el.setAttribute(attr, val);
}

/** HTML構造に応じて記事・コラムタブのセクションIDを解決する */
export function getArticlesTabId() {
  const candidates = ["tab-articles", "tab-columns", "tab-column"];
  for (let i = 0; i < candidates.length; i++) {
    if (document.getElementById(candidates[i])) return candidates[i];
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

function getArticleViewElements(sectionEl) {
  return {
    listView: queryFirst(sectionEl, ["#articles-list-view", "#column-list-view"]),
    detailView: queryFirst(sectionEl, ["#article-detail-view", "#column-detail-view"])
  };
}

function setArticleListViewVisible(sectionEl, views, visible) {
  if (views.listView) {
    views.listView.style.display = visible ? "block" : "none";
  } else {
    Array.from(sectionEl.children).forEach(function (ch) {
      if (ch !== views.detailView) ch.style.display = visible ? "" : "none";
    });
  }
}

function buildArticleShareButtonsHtml(article, xLabel) {
  return (
    '<div class="article-share-actions">' +
    '<button type="button" class="action-btn share-article-x-btn" data-share-id="' +
    escapeHtml(article.id) + '" data-share-title="' + escapeHtml(article.title) +
    '" data-share-cat="' + escapeHtml(article.category || "記事・コラム") + '">' +
    xLabel + "</button>" +
    '<button type="button" class="action-btn copy-article-url-btn" data-share-id="' +
    escapeHtml(article.id) + '">🔗 個別URLをコピー</button>' +
    "</div>"
  );
}

function buildArticleThumbHtml(thumbUrl, title, imgClass, placeholderLabel) {
  return thumbUrl
    ? '<img src="' + escapeHtml(thumbUrl) + '" alt="' + escapeHtml(title) +
      '" class="' + imgClass + '" loading="lazy" decoding="async" referrerpolicy="no-referrer" />'
    : '<div class="article-thumb-placeholder"><span>' + placeholderLabel + "</span></div>";
}

/** 開いている記事に応じてページtitleおよびOGP/canonicalメタタグを更新する */
export function updatePageSeoMeta(article) {
  if (article && article.title) {
    const fullTitle = article.title + " | 週刊VOCALOID™複合ランキング";
    const desc =
      article.summary ||
      article.title + " - 週刊VOCALOID™複合ランキング（" + (article.category || "コラム") + "）";
    const articleUrl = OFFICIAL_SITE_URL + "/articles/" + encodeURIComponent(article.id) + ".html";

    document.title = fullTitle;
    setMetaAttr('meta[name="description"]', "content", desc);
    setMetaAttr('meta[property="og:title"]', "content", fullTitle);
    setMetaAttr('meta[property="og:description"]', "content", desc);
    setMetaAttr('meta[property="og:url"]', "content", articleUrl);
    setMetaAttr('link[rel="canonical"]', "href", articleUrl);
  } else {
    document.title = DEFAULT_PAGE_TITLE;
    setMetaAttr('meta[name="description"]', "content", DEFAULT_META_DESC);
    setMetaAttr('meta[property="og:title"]', "content", DEFAULT_PAGE_TITLE);
    setMetaAttr('meta[property="og:description"]', "content", DEFAULT_META_DESC);
    setMetaAttr('meta[property="og:url"]', "content", OFFICIAL_SITE_URL);
    setMetaAttr('link[rel="canonical"]', "href", OFFICIAL_SITE_URL);
  }
}

/** 記事オブジェクトから安全なサムネイル画像URLを解決する */
export function resolveArticleThumbnail(article) {
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

/** 記事の公開日時を「YYYY.MM.DD」形式へ整形する */
export function formatArticleDate(article) {
  const raw = article.publishedAt || article.publishAt || article.updatedAt || "";
  const m = String(raw).match(/(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
  if (m) return m[1] + "." + String(m[2]).padStart(2, "0") + "." + String(m[3]).padStart(2, "0");
  return raw || "";
}

/** 現在のカテゴリと検索クエリで記事一覧を絞り込む */
export function getFilteredArticles() {
  return state.allArticlesData.filter(function (a) {
    if (state.currentArticleCategory !== "all" && (a.category || "") !== state.currentArticleCategory) {
      return false;
    }
    if (state.currentArticleSearchQuery) {
      const tagsStr = Array.isArray(a.tags) ? a.tags.join(" ") : String(a.tags || "");
      const hay = (
        (a.title || "") + " " + (a.summary || "") + " " + (a.category || "") + " " +
        tagsStr + " " + (a.author || "")
      ).toLowerCase();
      if (hay.indexOf(state.currentArticleSearchQuery) === -1) return false;
    }
    return true;
  });
}

/** 記事タグ配列からタグ一覧HTMLを生成する */
export function buildArticleTagRowHtml(tags) {
  if (!Array.isArray(tags) || !tags.length) return "";
  const spans = tags.map(function (t) {
    return '<span class="article-tag">#' + escapeHtml(t) + "</span>";
  });
  return '<div class="article-tag-row">' + spans.join("") + "</div>";
}

/** 記事個別HTMLページの相対パーマリンクを返す */
export function getArticlePermalink(article) {
  return "./articles/" + encodeURIComponent(String(article.id || "").trim()) + ".html";
}

/** ピックアップ特集記事のヒーローカードHTMLを生成する */
export function buildHeroArticleHtml(heroArticle) {
  const thumbInner = buildArticleThumbHtml(
    resolveArticleThumbnail(heroArticle),
    heroArticle.title,
    "article-hero-thumb",
    "VOCALOID COLUMN"
  );
  const dateStr = formatArticleDate(heroArticle);
  const tags = Array.isArray(heroArticle.tags) ? heroArticle.tags : [];
  const permalink = getArticlePermalink(heroArticle);
  const authorHtml = heroArticle.author ? '<span class="article-author">by ' + escapeHtml(heroArticle.author) + "</span>" : "";

  return (
    '<article class="article-hero-card" data-article-id="' + escapeHtml(heroArticle.id) + '">' +
    '<div class="article-hero-thumb-wrap">' + thumbInner + '<span class="article-pickup-ribbon">PICK UP 特集</span></div>' +
    '<div class="article-hero-body">' +
    '<div class="article-card-meta"><span class="article-cat-badge">' + escapeHtml(heroArticle.category || "コラム") +
    '</span><time class="article-date">' + escapeHtml(dateStr) + "</time>" + authorHtml + "</div>" +
    '<h3 class="article-hero-title"><a href="' + escapeHtml(permalink) +
    '" class="article-seo-link" style="color:inherit;text-decoration:none;">' + escapeHtml(heroArticle.title) + "</a></h3>" +
    '<p class="article-hero-summary">' + escapeHtml(heroArticle.summary || "") + "</p>" +
    buildArticleTagRowHtml(tags) +
    '<a href="' + escapeHtml(permalink) + '" class="article-read-more article-seo-link" style="text-decoration:none;">記事を読む ➔</a>' +
    "</div></article>"
  );
}

/** 一覧グリッドおよび関連記事用の記事カードHTMLを生成する */
export function buildGridArticleCardHtml(art) {
  const thumbInner = buildArticleThumbHtml(
    resolveArticleThumbnail(art),
    art.title,
    "article-card-thumb",
    "COLUMN"
  );
  const dateStr = formatArticleDate(art);
  const tags = Array.isArray(art.tags) ? art.tags.slice(0, 4) : [];
  const permalink = getArticlePermalink(art);
  const authorHtml = art.author ? '<span class="article-author">' + escapeHtml(art.author) + "</span>" : "";

  return (
    '<article class="article-card" data-article-id="' + escapeHtml(art.id) + '">' +
    '<div class="article-card-thumb-wrap">' + thumbInner +
    '<span class="article-cat-badge overlay-badge">' + escapeHtml(art.category || "コラム") + "</span></div>" +
    '<div class="article-card-body">' +
    '<div class="article-card-meta"><time class="article-date">' + escapeHtml(dateStr) + "</time>" + authorHtml + "</div>" +
    '<h3 class="article-card-title"><a href="' + escapeHtml(permalink) +
    '" class="article-seo-link" style="color:inherit;text-decoration:none;">' + escapeHtml(art.title) + "</a></h3>" +
    '<p class="article-card-summary">' + escapeHtml(art.summary || "") + "</p>" +
    buildArticleTagRowHtml(tags) +
    "</div></article>"
  );
}

/** 記事・コラム一覧ビュー（ピックアップ＋グリッド）を描画する */
export function renderArticlesView() {
  const sectionEl = document.getElementById(getArticlesTabId());
  if (!sectionEl) return;

  const featuredContainer = queryFirst(sectionEl, ["#articles-featured-container", "#column-featured-container", "#articles-featured"]);
  const gridContainer = queryFirst(sectionEl, ["#articles-grid", "#column-grid", "#articles-container", "#column-list"]);
  const emptyStateEl = queryFirst(sectionEl, ["#column-empty-state", "#articles-empty-state"]);
  if (!gridContainer) return;

  if (!state.allArticlesData.length) {
    if (featuredContainer) featuredContainer.innerHTML = "";
    if (emptyStateEl) {
      emptyStateEl.style.display = "block";
      gridContainer.innerHTML = "";
    } else {
      gridContainer.innerHTML =
        '<div class="articles-empty-card"><div class="articles-empty-badge">COMING SOON</div>' +
        '<h3 class="articles-empty-title">記事・コラムは現在準備中です</h3><p class="articles-empty-desc">' +
        "このタブでは、週間チャートの深掘りトレンド考察、注目ボカロP・新曲の特集レビュー、対話形式のコラム記事を不定期で公開していきます。<br>" +
        "第1弾の記事公開まで今しばらくお待ちください！</p></div>";
    }
    return;
  }

  if (emptyStateEl) emptyStateEl.style.display = "none";

  const filtered = getFilteredArticles();
  if (!filtered.length) {
    if (featuredContainer) featuredContainer.innerHTML = "";
    gridContainer.innerHTML = '<div class="empty-state">条件に一致する記事・コラムが見つかりませんでした。</div>';
    return;
  }

  const showHero = state.currentArticleCategory === "all" && !state.currentArticleSearchQuery;
  const heroArticle = showHero ? filtered.find(function (a) { return Boolean(a.featured); }) || filtered[0] : null;
  const gridList = heroArticle && featuredContainer ? filtered.filter(function (a) { return a.id !== heroArticle.id; }) : filtered;

  if (featuredContainer) featuredContainer.innerHTML = heroArticle ? buildHeroArticleHtml(heroArticle) : "";
  if (!gridList.length && heroArticle && featuredContainer) {
    gridContainer.innerHTML = "";
    return;
  }

  gridContainer.innerHTML = gridList.map(buildGridArticleCardHtml).join("");
}

/** 指定IDの記事をオンデマンド読込し、詳細リーダービューを開く */
export async function openArticleById(articleId, updateHash, ensureLoadedFn) {
  if (typeof ensureLoadedFn === "function") await ensureLoadedFn();
  let article = state.allArticlesData.find(function (a) { return String(a.id) === String(articleId); });
  if (!article) {
    showToast("指定された記事が見つかりません");
    return;
  }

  // 軽量インデックス(articles_index.json)から読み込まれていて本文(body)が未取得の場合、オンデマンドで個別記事JSONを取得
  if (!article.body && !article.content) {
    const cleanId = encodeURIComponent(String(article.id).trim());
    const fullArticle = await fetchJsonWithFallback(
      ["./data/articles/" + cleanId + ".json", "public/data/articles/" + cleanId + ".json", "./data/articles.json"],
      "default"
    );
    if (fullArticle) {
      if (Array.isArray(fullArticle.articles)) {
        const found = fullArticle.articles.find(function (x) { return String(x.id) === String(articleId); });
        if (found) Object.assign(article, found);
      } else if (fullArticle.body || fullArticle.content) {
        Object.assign(article, fullArticle);
      }
    }
  }

  state.currentOpenArticleId = article.id;
  if (updateHash) history.pushState(null, "", "#article=" + encodeURIComponent(article.id));
  updatePageSeoMeta(article);

  const sectionEl = document.getElementById(getArticlesTabId());
  if (!sectionEl) return;
  const views = getArticleViewElements(sectionEl);
  if (!views.detailView) return;

  setArticleListViewVisible(sectionEl, views, false);

  const thumbUrl = resolveArticleThumbnail(article);
  const dateStr = formatArticleDate(article);
  const tags = Array.isArray(article.tags) ? article.tags : [];
  const bodyHtml = parseArticleBodyHtml(article.body || article.content || "");
  const related = state.allArticlesData.filter(function (a) { return a.id !== article.id; }).slice(0, 3);

  const authorHtml = article.author ? '<span class="article-author">執筆: ' + escapeHtml(article.author) + "</span>" : "";
  const heroImgHtml = thumbUrl
    ? '<div class="article-reader-hero-img-wrap"><img src="' + escapeHtml(thumbUrl) +
      '" alt="' + escapeHtml(article.title) + '" class="article-reader-hero-img" referrerpolicy="no-referrer" /></div>'
    : "";
  const leadHtml = article.summary ? '<div class="article-reader-lead">' + escapeHtml(article.summary).replace(/\n/g, "<br>") + "</div>" : "";
  const relatedHtml = related.length
    ? '<div class="article-related-section"><h3 class="section-title">その他の記事・コラム</h3>' +
      '<div class="articles-grid related-grid">' + related.map(buildGridArticleCardHtml).join("") + "</div></div>"
    : "";

  views.detailView.style.display = "block";
  views.detailView.innerHTML =
    '<div class="article-reader-card"><div class="article-reader-topbar">' +
    '<button type="button" id="article-back-btn" class="article-back-btn">← 記事一覧へ戻る</button>' +
    buildArticleShareButtonsHtml(article, "𝕏 記事をシェア") + "</div>" +
    '<header class="article-reader-header"><div class="article-card-meta">' +
    '<span class="article-cat-badge">' + escapeHtml(article.category || "コラム") + "</span>" +
    '<time class="article-date">公開: ' + escapeHtml(dateStr) + "</time>" + authorHtml + "</div>" +
    '<h1 class="article-reader-title">' + escapeHtml(article.title) + "</h1>" +
    buildArticleTagRowHtml(tags) + "</header>" +
    heroImgHtml + leadHtml + '<div class="article-reader-content">' + bodyHtml + "</div>" +
    '<footer class="article-reader-footer"><div class="article-share-box"><span>この記事をシェアする：</span>' +
    buildArticleShareButtonsHtml(article, "𝕏 ポストする") + "</div>" +
    '<button type="button" class="article-back-btn bottom-back-btn">← 記事・コラム一覧へ戻る</button>' +
    "</footer></div>" + relatedHtml;

  window.scrollTo({ top: 0, behavior: "smooth" });
}

/** 記事詳細リーダーを閉じ、一覧ビューとSEOメタ情報を元に戻す */
export function closeArticleDetail(clearHash) {
  state.currentOpenArticleId = null;
  updatePageSeoMeta(null);
  if (clearHash && window.location.hash.indexOf("#article=") === 0) {
    history.pushState(null, "", window.location.pathname + window.location.search);
  }
  const sectionEl = document.getElementById(getArticlesTabId());
  if (!sectionEl) return;

  const views = getArticleViewElements(sectionEl);
  if (views.detailView) views.detailView.style.display = "none";
  setArticleListViewVisible(sectionEl, views, true);
}
