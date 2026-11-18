import re
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name in ("backend", "scripts", "src") else BASE_DIR
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from archive_manager import (
    ARCHIVE_DIR,
    ARCHIVE_INDEX,
    ARTICLES_MASTER_FILE,
    BACKUP_DRAFT_FILE,
    DRAFT_FILE,
    JST,
    LOCAL_PATH_PATTERNS,
    PUBLIC_ARTICLES_FILE,
    PUBLIC_LATEST,
    SECRET_PATTERNS,
    archive_existing_latest,
    get_release_datetime_jst,
    infer_archive_id_and_period,
    inspect_and_redact_text,
    is_chart_released,
    load_json,
    normalize_period_str,
    rebuild_archive_index,
    rescue_and_repair_past_archives,
    rollback_unreleased_public_files,
    save_json,
    update_archive_index,
)
from article_publisher import (
    _generate_static_article_html,
    _render_article_body_static_html,
    is_article_released,
    sync_published_articles,
)

# 水曜13:00のアクセス集中をCloudflareエッジで高速吸収するキャッシュ＆セキュリティヘッダー定義
CLOUDFLARE_HEADERS_CONTENT = """/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin

/index.html
  Cache-Control: public, max-age=0, s-maxage=60, stale-while-revalidate=86400

/app.js
  Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=86400

/js/app.js
  Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=86400

/js/*
  Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=86400

/style.css
  Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=86400

/css/style.css
  Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=86400

/data/latest_ranking.json
  Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=86400

/public/data/latest_ranking.json
  Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=86400

/data/articles.json
  Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=86400

/public/data/articles.json
  Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=86400

/data/archive_index.json
  Cache-Control: public, max-age=60, s-maxage=120, stale-while-revalidate=86400

/data/archives/archive_index.json
  Cache-Control: public, max-age=60, s-maxage=120, stale-while-revalidate=86400

/data/archives/*
  Cache-Control: public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800
"""


def sanitize_frontend_content(text, filename=""):
    """コードブロック記法やローカルパス・機密情報を除去・サニタイズする"""
    if not text:
        return text
    cleaned = text.strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\r?\n", "", cleaned)
    cleaned = re.sub(r"\r?\n```$", "", cleaned)
    cleaned = inspect_and_redact_text(cleaned, label=filename)
    return cleaned + "\n"


def sync_frontend_assets():
    """HTML/CSS/ES Modules(public/js/*.js)およびCloudflare _headersを検証・同期する"""
    asset_groups = {
        "index.html": [PROJECT_ROOT / "public/index.html", PROJECT_ROOT / "index.html"],
        "style.css": [PROJECT_ROOT / "public/style.css", PROJECT_ROOT / "public/css/style.css", PROJECT_ROOT / "style.css"],
    }
    public_targets = {
        "index.html": [PROJECT_ROOT / "public/index.html"],
        "style.css": [PROJECT_ROOT / "public/style.css", PROJECT_ROOT / "public/css/style.css"],
    }

    for name, candidates in asset_groups.items():
        existing = [p for p in candidates if p.exists() and p.is_file() and p.stat().st_size > 0]
        if not existing:
            continue
        newest_file = max(existing, key=lambda p: p.stat().st_mtime)
        raw_content = newest_file.read_text(encoding="utf-8")
        clean_content = sanitize_frontend_content(raw_content, filename=name)
        for target in public_targets[name]:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_text(encoding="utf-8") != clean_content:
                target.write_text(clean_content, encoding="utf-8")
        print(f"[SYNC & SECURE] {name} を検証・同期しました (source: {newest_file.relative_to(PROJECT_ROOT)})")

    js_dir = PROJECT_ROOT / "public/js"
    if js_dir.exists() and js_dir.is_dir():
        for js_path in sorted(js_dir.glob("*.js")):
            if not js_path.is_file() or js_path.stat().st_size == 0:
                continue
            raw_content = js_path.read_text(encoding="utf-8")
            clean_content = sanitize_frontend_content(raw_content, filename=js_path.name)
            if clean_content != raw_content:
                js_path.write_text(clean_content, encoding="utf-8")
            print(f"[SYNC & SECURE] js/{js_path.name} を検証しました")

    for headers_target in (PROJECT_ROOT / "_headers", PROJECT_ROOT / "public/_headers"):
        headers_target.parent.mkdir(parents=True, exist_ok=True)
        headers_target.write_text(CLOUDFLARE_HEADERS_CONTENT, encoding="utf-8")
    print("[SYNC & SECURE] Cloudflare エッジキャッシュ設定 (_headers) を更新しました")


def _load_latest_draft():
    candidates = [
        DRAFT_FILE,
        PROJECT_ROOT / "data/drafts/weekly_draft.json",
        PROJECT_ROOT / "data/weekly_draft.json",
        BACKUP_DRAFT_FILE,
    ]
    for cand in candidates:
        loaded = load_json(cand)
        if isinstance(loaded, dict) and (loaded.get("songs") or loaded.get("ranking")):
            return loaded, cand
    return None, DRAFT_FILE


def main(force_publish: bool = False):
    if "--force" in sys.argv:
        force_publish = True

    print("=== 週刊VOCALOID複合ランキング 公開・予約管理処理開始 ===")
    now_dt = datetime.now(JST)

    sync_frontend_assets()
    sync_published_articles(now_dt)

    draft_data, used_draft_path = _load_latest_draft()
    if not isinstance(draft_data, dict):
        archive_existing_latest()
        rescue_and_repair_past_archives()
        rebuild_archive_index(now_dt)
        print("[INFO] weekly_draft.json が見つからないため、アーカイブ復旧・記事・アセット同期のみ完了しました。")
        return False

    publish_date = draft_data.get("publishDate") or now_dt.strftime("%Y-%m-%d")
    archive_id = draft_data.get("archiveId") or publish_date
    publish_at = draft_data.get("publishAt") or f"{publish_date}T13:00:00+09:00"
    period_str = normalize_period_str(draft_data.get("period"), now_dt)
    now_str = now_dt.strftime("%Y-%m-%d %H:%M")

    # 既存公開分の退避・過去アーカイブ救出＆月曜確定値修復
    archive_existing_latest(incoming_archive_id=archive_id)
    rescue_and_repair_past_archives(current_archive_id=archive_id)

    songs = draft_data.get("ranking") or draft_data.get("songs") or []
    for idx, s in enumerate(songs, start=1):
        if isinstance(s, dict):
            if not s.get("rank"):
                s["rank"] = idx
            if not isinstance(s.get("chart_in_count"), int) or s.get("chart_in_count", 0) < 1:
                s["chart_in_count"] = 1

    draft_data.update({
        "songs": songs,
        "ranking": songs,
        "publishDate": publish_date,
        "publishAt": publish_at,
        "archiveId": archive_id,
        "period": period_str,
        "updated_at": draft_data.get("updated_at") or now_str,
    })

    save_json(used_draft_path, draft_data)
    if DRAFT_FILE.resolve() != used_draft_path.resolve():
        save_json(DRAFT_FILE, draft_data)
    alt_draft = PROJECT_ROOT / "data" / "weekly_draft.json"
    if alt_draft.resolve() != DRAFT_FILE.resolve():
        save_json(alt_draft, draft_data)

    release_dt = get_release_datetime_jst(draft_data)
    if not force_publish and now_dt < release_dt:
        rollback_unreleased_public_files(now_dt)
        print(
            f"[SCHEDULED / 予約待機中] 解禁日時 ({release_dt.strftime('%Y-%m-%d %H:%M JST')}) より前のため、"
            f"本番サイトの表示は前週のまま維持し、今週のランキング・執筆原稿を予約保存しました。"
        )
        return False

    draft_data["published_at"] = now_str
    save_json(PUBLIC_LATEST, draft_data)
    save_json(PROJECT_ROOT / "data/latest_ranking.json", draft_data)
    save_json(ARCHIVE_DIR / f"{archive_id}.json", draft_data)
    rebuild_archive_index(now_dt)

    print(f"[OK] 解禁日時到達を確認し、最新ランキングを本番サイトへ公開しました: {PUBLIC_LATEST}")
    return True


if __name__ == "__main__":
    main()
