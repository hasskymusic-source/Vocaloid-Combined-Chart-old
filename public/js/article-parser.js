/**
 * 記事・コラム本文のMarkdownおよび対話・ポイント・動画埋め込みショートコードパーサー
 */
import {
  escapeHtml,
  sanitizeSafeImageUrl,
  sanitizeYoutubeId,
  sanitizeNiconicoId
} from "./utils.js";

/** 左右対話吹き出しのHTMLを生成する */
export function renderTalkBubbleHtml(side, name, icon, color, messageText) {
  const cleanSide = String(side || "left").toLowerCase() === "right" ? "right" : "left";
  const safeName = escapeHtml(name || "話し手");
  const safeColor = /^#[0-9A-Fa-f]{3,8}$/.test((color || "").trim()) ? color.trim() : "#00d2ff";
  const safeImgUrl = sanitizeSafeImageUrl(icon);

  const avatarInner = safeImgUrl
    ? '<img src="' +
      escapeHtml(safeImgUrl) +
      '" alt="' +
      safeName +
      '" class="talk-avatar-img" referrerpolicy="no-referrer" />'
    : '<span class="talk-avatar-emoji">' +
      escapeHtml(icon || safeName.slice(0, 2) || "💬") +
      "</span>";

  const formattedMsg = formatInlineMarkdown(messageText || "").replace(/\n/g, "<br>");

  return (
    '<div class="talk-row talk-' +
    cleanSide +
    '">' +
    '<div class="talk-speaker-col">' +
    '<div class="talk-avatar" style="border-color: ' +
    safeColor +
    ';">' +
    avatarInner +
    "</div>" +
    '<span class="talk-speaker-name">' +
    safeName +
    "</span>" +
    "</div>" +
    '<div class="talk-bubble" style="--speaker-color: ' +
    safeColor +
    ';">' +
    '<div class="talk-bubble-text">' +
    formattedMsg +
    "</div>" +
    "</div>" +
    "</div>"
  );
}

/** 記事内の楽曲・動画埋め込みカードのHTMLを生成する */
export function renderVideoEmbedCardHtml(ytId, ncId, titleStr) {
  const safeYt = sanitizeYoutubeId(ytId);
  const safeNc = sanitizeNiconicoId(ncId);
  const thumb = safeYt ? "https://i.ytimg.com/vi/" + safeYt + "/mqdefault.jpg" : "";
  const safeTitle = escapeHtml(titleStr || "関連楽曲・動画リンク");

  const thumbHtml = thumb
    ? '<img src="' +
      escapeHtml(thumb) +
      '" alt="' +
      safeTitle +
      '" class="article-video-thumb" loading="lazy" referrerpolicy="no-referrer" />'
    : "";

  const ytBtn = safeYt
    ? '<a href="https://www.youtube.com/watch?v=' +
      encodeURIComponent(safeYt) +
      '" target="_blank" rel="noopener noreferrer" class="video-link yt-link">▶ YouTubeで視聴</a>'
    : "";

  const ncBtn = safeNc
    ? '<a href="https://www.nicovideo.jp/watch/' +
      encodeURIComponent(safeNc) +
      '" target="_blank" rel="noopener noreferrer" class="video-link nc-link">▶ ニコニコ動画で視聴</a>'
    : "";

  return (
    '<div class="article-video-card">' +
    thumbHtml +
    '<div class="article-video-info">' +
    '<div class="article-video-title">🎵 ' +
    safeTitle +
    "</div>" +
    '<div class="article-video-links">' +
    ytBtn +
    ncBtn +
    "</div>" +
    "</div>" +
    "</div>"
  );
}

/** インラインMarkdown（太字・コード・リンク）を安全なHTMLへ変換する */
export function formatInlineMarkdown(rawText) {
  let s = escapeHtml(rawText);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return s;
}

/** ショートコード属性文字列をオブジェクトへパースする */
export function parseShortcodeAttrs(attrStr) {
  const attrs = {};
  const regex = /([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"/g;
  let m;
  while ((m = regex.exec(attrStr)) !== null) {
    attrs[m[1]] = m[2];
  }
  return attrs;
}

/** 記事本文（Markdownおよび独自ショートコード）を記事リーダー用HTMLへ変換する */
export function parseArticleBodyHtml(rawBody) {
  if (!rawBody || typeof rawBody !== "string") return "";

  const placeholders = [];
  const pushPlaceholder = function (html) {
    const token = "@@__ARTICLE_BLOCK_" + placeholders.length + "__@@";
    placeholders.push(html);
    return "\n" + token + "\n";
  };

  let text = rawBody.replace(/\r\n/g, "\n");

  text = text.replace(/\[talk([^\]]*)\]([\s\S]*?)\[\/talk\]/gi, function (_, attrStr, inner) {
    const attrs = parseShortcodeAttrs(attrStr);
    return pushPlaceholder(
      renderTalkBubbleHtml(
        attrs.side || "left",
        attrs.name || "",
        attrs.icon || "🎧",
        attrs.color || "#00d2ff",
        inner.trim()
      )
    );
  });

  text = text.replace(/^:::talk\s+([^\n]+)\n([\s\S]*?)^:::\s*$/gm, function (_, headerLine, inner) {
    const parts = headerLine.split("|").map(function (p) {
      return p.trim();
    });
    return pushPlaceholder(
      renderTalkBubbleHtml(
        parts[0] || "left",
        parts[1] || "話し手",
        parts[2] || "💬",
        parts[3] || "#00d2ff",
        inner.trim()
      )
    );
  });

  text = text.replace(/\[point([^\]]*)\]([\s\S]*?)\[\/point\]/gi, function (_, attrStr, inner) {
    const attrs = parseShortcodeAttrs(attrStr);
    const title = escapeHtml(attrs.title || "POINT");
    const content = formatInlineMarkdown(inner.trim()).replace(/\n/g, "<br>");
    return pushPlaceholder(
      '<div class="article-point-box">' +
        '<div class="article-point-title">💡 ' +
        title +
        "</div>" +
        '<div class="article-point-body">' +
        content +
        "</div>" +
        "</div>"
    );
  });

  text = text.replace(/^:::point\s*([^\n]*)\n([\s\S]*?)^:::\s*$/gm, function (_, titleLine, inner) {
    const title = escapeHtml(titleLine.trim() || "POINT");
    const content = formatInlineMarkdown(inner.trim()).replace(/\n/g, "<br>");
    return pushPlaceholder(
      '<div class="article-point-box">' +
        '<div class="article-point-title">💡 ' +
        title +
        "</div>" +
        '<div class="article-point-body">' +
        content +
        "</div>" +
        "</div>"
    );
  });

  text = text.replace(/\[video([^\]]*)\]/gi, function (_, attrStr) {
    const attrs = parseShortcodeAttrs(attrStr);
    return pushPlaceholder(
      renderVideoEmbedCardHtml(attrs.yt || "", attrs.nc || "", attrs.title || "")
    );
  });

  const lines = text.split("\n");
  const outHtml = [];
  let inList = false;

  const closeListIfNeeded = function () {
    if (inList) {
      outHtml.push("</ul>");
      inList = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      closeListIfNeeded();
      continue;
    }

    const tokenMatch = trimmed.match(/^@@__ARTICLE_BLOCK_(\d+)__@@$/);
    if (tokenMatch) {
      closeListIfNeeded();
      outHtml.push(placeholders[parseInt(tokenMatch[1], 10)]);
      continue;
    }

    const quickTalkMatch = trimmed.match(
      /^\[(left\vert{}right):([^:\]]+)(?::([^:\]]+))?(?::(#[0-9A-Fa-f]{3,8}))?\]\s*(.+)$/i
    );
    if (quickTalkMatch) {
      closeListIfNeeded();
      outHtml.push(
        renderTalkBubbleHtml(
          quickTalkMatch[1],
          quickTalkMatch[2],
          quickTalkMatch[3] || "💬",
          quickTalkMatch[4] || "#00d2ff",
          quickTalkMatch[5]
        )
      );
      continue;
    }

    if (trimmed === "---" || trimmed === "***") {
      closeListIfNeeded();
      outHtml.push('<hr class="article-divider" />');
      continue;
    }

    if (trimmed.indexOf("### ") === 0) {
      closeListIfNeeded();
      outHtml.push('<h3 class="article-h3">' + formatInlineMarkdown(trimmed.slice(4)) + "</h3>");
      continue;
    }

    if (trimmed.indexOf("## ") === 0) {
      closeListIfNeeded();
      outHtml.push('<h2 class="article-h2">' + formatInlineMarkdown(trimmed.slice(3)) + "</h2>");
      continue;
    }

    if (trimmed.indexOf("> ") === 0) {
      closeListIfNeeded();
      outHtml.push(
        '<blockquote class="article-quote">' + formatInlineMarkdown(trimmed.slice(2)) + "</blockquote>"
      );
      continue;
    }

    if (trimmed.indexOf("- ") === 0 || trimmed.indexOf("・") === 0) {
      if (!inList) {
        outHtml.push('<ul class="article-ul">');
        inList = true;
      }
      const itemText = trimmed.indexOf("- ") === 0 ? trimmed.slice(2) : trimmed.slice(1);
      outHtml.push("<li>" + formatInlineMarkdown(itemText.trim()) + "</li>");
      continue;
    }

    closeListIfNeeded();
    outHtml.push('<p class="article-p">' + formatInlineMarkdown(trimmed) + "</p>");
  }

  closeListIfNeeded();
  return outHtml.join("\n");
}
