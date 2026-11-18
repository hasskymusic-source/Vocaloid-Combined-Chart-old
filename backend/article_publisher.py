import html as _html
import json
import re
import sys
import urllib.parse as _up
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name in ("backend", "scripts", "src") else BASE_DIR
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from archive_manager import (
    ARTICLES_MASTER_FILE,
    JST,
    PUBLIC_ARTICLES_FILE,
    inspect_and_redact_text,
    load_json,
    save_json,
)


def is_article_released(article: dict, now_dt: datetime = None) -> bool:
    """
    記事・コラムの公開判定：
    - status が 'draft'（下書き）の場合は非公開
    - publishAt（予約公開日時）が設定されており、現在時刻がまだ到達していない場合は非公開
    """
    if not isinstance(article, dict):
        return False
    if str(article.get("status", "published")).lower() == "draft":
        return False

    if now_dt is None:
        now_dt = datetime.now(JST)

    pub_at_str = article.get("publishAt") or ""
    if pub_at_str and isinstance(pub_at_str, str):
        try:
            cleaned = pub_at_str.strip()
            if cleaned.endswith("Z"):
                cleaned = cleaned[:-1] + "+00:00"
            dt = datetime.fromisoformat(cleaned)
            dt = dt.replace(tzinfo=JST) if dt.tzinfo is None else dt.astimezone(JST)
            if now_dt < dt:
                return False
        except Exception:
            pass

    return True


def _esc(s):
    return _html.escape(str(s or ""), quote=True)


def _inline_md(s):
    escaped = _esc(s)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        escaped,
    )


def _parse_attrs(attr_str):
    return dict(re.findall(r'([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', attr_str or ""))


def _talk_html(side, name, icon, color, msg):
    clean_side = "right" if str(side).lower() == "right" else "left"
    safe_name = _esc(name or "話し手")
    safe_color = color.strip() if re.match(r"^#[0-9A-Fa-f]{3,8}$", str(color or "").strip()) else "#00d2ff"
    icon_str = str(icon or "").strip()
    if icon_str.startswith(("https://", "http://", "/", "./", "data:image/")):
        avatar_inner = f'<img src="{_esc(icon_str)}" alt="{safe_name}" class="talk-avatar-img" loading="lazy" referrerpolicy="no-referrer" />'
    else:
        avatar_inner = f'<span class="talk-avatar-emoji">{_esc(icon_str or safe_name[:2] or "💬")}</span>'
    body_html = _inline_md(msg).replace("\n", "<br>")
    return (
        f'<div class="talk-row talk-{clean_side}">'
        f'<div class="talk-speaker-col"><div class="talk-avatar" style="border-color: {safe_color};">{avatar_inner}</div>'
        f'<span class="talk-speaker-name">{safe_name}</span></div>'
        f'<div class="talk-bubble" style="--speaker-color: {safe_color};"><div class="talk-bubble-text">{body_html}</div></div></div>'
    )


def _render_article_body_static_html(raw_body: str) -> str:
    """記事本文（Markdown＋左右対話タグ）を静的HTMLへ変換するサーバーサイドレンダラー"""
    if not raw_body or not isinstance(raw_body, str):
        return ""
    placeholders = []
    def _push_ph(html_str):
        placeholders.append(html_str)
        return f"\n@@__STATIC_BLOCK_{len(placeholders) - 1}__@@\n"

    text = raw_body.replace("\r\n", "\n")
    text = re.sub(
        r"\[talk([^\]]*)\]([\s\S]*?)\[/talk\]",
        lambda m: _push_ph(_talk_html(**{k: _parse_attrs(m.group(1)).get(k, d) for k, d in [("side", "left"), ("name", ""), ("icon", "🎧"), ("color", "#00d2ff")]}, msg=m.group(2).strip())),
        text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\[point([^\]]*)\]([\s\S]*?)\[/point\]",
        lambda m: _push_ph(f'<div class="article-point-box"><div class="article-point-title">💡 {_esc(_parse_attrs(m.group(1)).get("title", "POINT"))}</div><div class="article-point-body">{_inline_md(m.group(2).strip()).replace(chr(10), "<br>")}</div></div>'),
        text, flags=re.IGNORECASE,
    )
    def _video_card(m):
        attrs = _parse_attrs(m.group(1))
        yt, nc = re.sub(r"[^A-Za-z0-9_-]", "", attrs.get("yt", "")), re.sub(r"[^A-Za-z0-9]", "", attrs.get("nc", ""))
        vtitle = _esc(attrs.get("title", "関連楽曲・動画リンク"))
        thumb = f'<img src="https://i.ytimg.com/vi/{yt}/mqdefault.jpg" alt="{vtitle}" class="article-video-thumb" loading="lazy" />' if yt else ""
        yt_btn = f'<a href="https://www.youtube.com/watch?v={yt}" target="_blank" rel="noopener noreferrer" class="video-link yt-link">▶ YouTubeで視聴</a>' if yt else ""
        nc_btn = f'<a href="https://www.nicovideo.jp/watch/{nc}" target="_blank" rel="noopener noreferrer" class="video-link nc-link">▶ ニコニコ動画で視聴</a>' if nc else ""
        return _push_ph(f'<div class="article-video-card">{thumb}<div class="article-video-info"><div class="article-video-title">🎵 {vtitle}</div><div class="article-video-links">{yt_btn}{nc_btn}</div></div></div>')

    text = re.sub(r"\[video([^\]]*)\]", _video_card, text, flags=re.IGNORECASE)

    out_lines = []
    in_list = False

    def _close_list():
        nonlocal in_list
        if in_list:
            out_lines.append("</ul>")
            in_list = False

    for line in text.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            _close_list()
            continue
        ph_m = re.match(r"^@@__STATIC_BLOCK_(\d+)__@@$", trimmed)
        if ph_m:
            _close_list()
            out_lines.append(placeholders[int(ph_m.group(1))])
        elif trimmed in ("---", "***"):
            _close_list()
            out_lines.append('<hr class="article-divider" />')
        elif trimmed.startswith(("### ", "## ", "> ")):
            _close_list()
            prefix_map = {"### ": ("h3", 4, "article-h3"), "## ": ("h2", 3, "article-h2"), "> ": ("blockquote", 2, "article-quote")}
            for pfx, (tag, offset, cls) in prefix_map.items():
                if trimmed.startswith(pfx):
                    out_lines.append(f'<{tag} class="{cls}">{_inline_md(trimmed[offset:])}</{tag}>')
                    break
        elif trimmed.startswith(("- ", "・")):
            if not in_list:
                out_lines.append('<ul class="article-ul">')
                in_list = True
            out_lines.append(f"<li>{_inline_md((trimmed[2:] if trimmed.startswith('- ') else trimmed[1:]).strip())}</li>")
        else:
            _close_list()
            out_lines.append(f'<p class="article-p">{_inline_md(trimmed)}</p>')
    _close_list()
    return "\n".join(out_lines)


def _generate_static_article_html(article: dict) -> str:
    """1記事ごとに固有のtitle, description, OGP, JSON-LD構造化データを持つ静的HTMLを生成"""
    aid = re.sub(r"[^A-Za-z0-9_-]", "", str(article.get("id") or "article"))
    title = str(article.get("title") or "記事・コラム").strip()
    category = str(article.get("category") or "コラム").strip()
    author = str(article.get("author") or "週刊VOCALOID複合チャート編集部").strip()
    pub_date = str(article.get("publishedAt") or article.get("publishAt") or "").strip()[:10]
    summary = str(article.get("summary") or "").strip()
    raw_body = str(article.get("body") or article.get("content") or "").strip()

    if not summary and raw_body:
        summary = re.sub(r"\s+", " ", re.sub(r"\[/?[^\]]+\]|[#*>_`]", "", raw_body)).strip()[:120]
    meta_desc = summary or f"{title} - 週刊VOCALOID™複合ランキング（{category}）"

    yt_id = re.sub(r"[^A-Za-z0-9_-]", "", str(article.get("youtubeId") or article.get("youtube_id") or ""))
    thumb_url = str(article.get("thumbnail") or "").strip() or (f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg" if yt_id else "")
    og_image_tag = f'<meta property="og:image" content="{_esc(thumb_url)}" />' if thumb_url else ""

    canonical_url = f"https://weekly-vocaloid-combined-chart.com/articles/{aid}.html"
    page_title = f"{title} | 週刊VOCALOID™複合ランキング"
    tags = article.get("tags") if isinstance(article.get("tags"), list) else []
    tags_html = '<div class="article-tag-row">' + "".join(f'<span class="article-tag">#{_esc(t)}</span>' for t in tags) + "</div>" if tags else ""
    hero_img_html = f'<div class="article-reader-hero-img-wrap"><img src="{_esc(thumb_url)}" alt="{_esc(title)}" class="article-reader-hero-img" referrerpolicy="no-referrer" /></div>' if thumb_url else ""
    lead_html = f'<div class="article-reader-lead">{_esc(summary).replace(chr(10), "<br>")}</div>' if summary else ""
    body_html = _render_article_body_static_html(raw_body)

    share_text = f"【{category}】{title}\n｜週刊VOCALOID™複合ランキング\n#週刊VOCALOID複合ランキング #ボカロ"
    share_x_url = f"https://twitter.com/intent/tweet?text={_up.quote(share_text)}&url={_up.quote(canonical_url)}"
    json_ld = json.dumps({
        "@context": "https://schema.org", "@type": "Article", "headline": title, "description": meta_desc,
        "datePublished": pub_date, "author": {"@type": "Organization", "name": author},
        "publisher": {"@type": "Organization", "name": "週刊VOCALOID複合ランキング"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(page_title)}</title>
  <meta name="description" content="{_esc(meta_desc)}" />
  <link rel="canonical" href="{_esc(canonical_url)}" />
  <meta property="og:site_name" content="週刊VOCALOID™複合ランキング" />
  <meta property="og:title" content="{_esc(page_title)}" />
  <meta property="og:description" content="{_esc(meta_desc)}" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="{_esc(canonical_url)}" />
  {og_image_tag}
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="stylesheet" href="../style.css" />
  <script type="application/ld+json">{json_ld}</script>
</head>
<body>
  <header class="site-header" style="padding-bottom: 1.25rem;">
    <div class="header-inner" style="margin-bottom: 0;">
      <div class="brand-area">
        <span class="brand-badge">WEEKLY VOCALOID COMBINED RANKING — COLUMN</span>
        <h1 class="site-title"><a href="../index.html" style="color: inherit; text-decoration: none;">週刊VOCALOID<sup class="tm-mark">TM</sup>複合ランキング</a></h1>
        <p class="site-subtitle">YouTube × ニコニコ動画 6指標統合ボカロチャート 記事・コラム</p>
      </div>
      <div class="header-controls">
        <a href="../index.html#tab-articles" class="action-btn" style="text-decoration: none;">← 記事・コラム一覧へ</a>
        <a href="../index.html" class="action-btn" style="text-decoration: none;">🏆 最新ランキング TOP 20</a>
      </div>
    </div>
  </header>
  <main class="main-container">
    <article class="article-reader-card">
      <div class="article-reader-topbar">
        <a href="../index.html#tab-articles" class="article-back-btn" style="text-decoration: none;">← 記事一覧へ戻る</a>
        <div class="article-share-actions">
          <a href="{_esc(share_x_url)}" target="_blank" rel="noopener noreferrer" class="action-btn" style="text-decoration: none;">𝕏 記事をシェア</a>
        </div>
      </div>
      <header class="article-reader-header">
        <div class="article-card-meta">
          <span class="article-cat-badge">{_esc(category)}</span>
          <time class="article-date">公開: {_esc(pub_date.replace('-', '.'))}</time>
          <span class="article-author">執筆: {_esc(author)}</span>
        </div>
        <h1 class="article-reader-title">{_esc(title)}</h1>
        {tags_html}
      </header>
      {hero_img_html}
      {lead_html}
      <div class="article-reader-content">{body_html}</div>
      <footer class="article-reader-footer">
        <div class="article-share-box">
          <span>この記事をシェアする：</span>
          <div class="article-share-actions">
            <a href="{_esc(share_x_url)}" target="_blank" rel="noopener noreferrer" class="action-btn" style="text-decoration: none;">𝕏 ポストする</a>
          </div>
        </div>
        <a href="../index.html#tab-articles" class="article-back-btn bottom-back-btn" style="text-decoration: none;">← 記事・コラム一覧へ戻る</a>
      </footer>
    </article>
  </main>
  <footer class="site-footer">
    <p>&copy; 週刊VOCALOID<sup class="tm-mark">TM</sup>複合ランキング All Rights Reserved.</p>
  </footer>
</body>
</html>
"""


def sync_published_articles(now_dt: datetime = None) -> list:
    """公開記事を抽出し、軽量インデックス・個別JSON・静的HTML・sitemap.xmlを一括同期する"""
    if now_dt is None:
        now_dt = datetime.now(JST)

    master_data = load_json(ARTICLES_MASTER_FILE, default={"articles": [], "speakers": []})
    raw_articles = master_data.get("articles", []) if isinstance(master_data, dict) else (master_data if isinstance(master_data, list) else [])

    published_list = [a for a in raw_articles if is_article_released(a, now_dt)]
    published_list.sort(
        key=lambda a: (1 if a.get("featured") else 0, str(a.get("publishedAt") or a.get("publishAt") or a.get("updatedAt") or "")),
        reverse=True,
    )

    now_str = now_dt.strftime("%Y-%m-%d %H:%M")
    lightweight_index = []
    for a in published_list:
        aid = re.sub(r"[^A-Za-z0-9_-]", "", str(a.get("id") or ""))
        if not aid:
            continue
        lightweight_index.append({
            "id": aid, "url": f"./articles/{aid}.html", "title": a.get("title", ""),
            "category": a.get("category", "コラム"), "featured": bool(a.get("featured", False)),
            "publishedAt": a.get("publishedAt") or a.get("publishAt") or "", "author": a.get("author", ""),
            "youtubeId": a.get("youtubeId") or a.get("youtube_id") or "", "thumbnail": a.get("thumbnail", ""),
            "tags": a.get("tags", []), "summary": a.get("summary", ""),
        })

    index_payload = {"updatedAt": now_str, "articles": lightweight_index}
    save_json(PROJECT_ROOT / "public/data/articles_index.json", index_payload)
    save_json(PROJECT_ROOT / "data/articles_index.json", index_payload)

    full_payload = {"updatedAt": now_str, "articles": published_list}
    save_json(PUBLIC_ARTICLES_FILE, full_payload)
    save_json(PROJECT_ROOT / "data/articles.json", full_payload)

    valid_filenames = {f"{re.sub(r'[^A-Za-z0-9_-]', '', str(a.get('id') or ''))}.html" for a in published_list}
    for target_dir in (PROJECT_ROOT / "public/articles", PROJECT_ROOT / "articles"):
        target_dir.mkdir(parents=True, exist_ok=True)
        for existing_html in target_dir.glob("*.html"):
            if existing_html.name not in valid_filenames:
                existing_html.unlink(missing_ok=True)

    sitemap_urls = ["https://weekly-vocaloid-combined-chart.com/"]
    for a in published_list:
        aid = re.sub(r"[^A-Za-z0-9_-]", "", str(a.get("id") or ""))
        if not aid:
            continue
        save_json(PROJECT_ROOT / f"public/data/articles/{aid}.json", a)
        save_json(PROJECT_ROOT / f"data/articles/{aid}.json", a)
        static_html = inspect_and_redact_text(_generate_static_article_html(a), label=f"{aid}.html")
        for out_html_path in (PROJECT_ROOT / f"public/articles/{aid}.html", PROJECT_ROOT / f"articles/{aid}.html"):
            out_html_path.write_text(static_html, encoding="utf-8")
        sitemap_urls.append(f"https://weekly-vocaloid-combined-chart.com/articles/{aid}.html")

    sitemap_entries = "\n".join(f"  <url><loc>{u}</loc></url>" for u in sitemap_urls)
    sitemap_xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{sitemap_entries}\n</urlset>\n'
    for sm_path in (PROJECT_ROOT / "public/sitemap.xml", PROJECT_ROOT / "sitemap.xml"):
        sm_path.write_text(sitemap_xml, encoding="utf-8")

    print(f"[SYNC & SECURE] 記事・コラムを公開同期しました (公開中: {len(published_list)} 件 / 個別HTML・sitemap生成済)")
    return published_list
