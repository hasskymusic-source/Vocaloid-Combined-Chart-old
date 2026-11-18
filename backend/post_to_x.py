import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import tweepy
except ImportError:
    tweepy = None

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name in ("backend", "scripts", "src") else BASE_DIR
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from archive_manager import (
    JST,
    PUBLIC_LATEST as CONFIG_PUBLIC_LATEST,
    infer_archive_id_and_period,
    is_chart_released,
    load_json,
    save_json,
)

PUBLIC_LATEST = CONFIG_PUBLIC_LATEST if CONFIG_PUBLIC_LATEST else (PROJECT_ROOT / "public" / "data" / "latest_ranking.json")
X_POST_HISTORY_FILE = PROJECT_ROOT / "data" / "x_post_history.json"
ENV_CANDIDATES = (PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local")


def _load_local_env():
    """ローカル手動実行用に .env / .env.local が存在すれば未設定の環境変数へ読み込む"""
    for env_path in ENV_CANDIDATES:
        if not env_path.exists() or not env_path.is_file():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                if key and val:
                    os.environ.setdefault(key, val)
        except Exception as e:
            print(f"[WARN] .env 読み込みをスキップしました ({env_path.name}): {e}")


def get_twitter_client():
    """環境変数（または .env）から X API v2 クライアントを生成する"""
    _load_local_env()
    env_map = {
        "X_API_KEY": os.environ.get("X_API_KEY", "").strip(),
        "X_API_SECRET": os.environ.get("X_API_SECRET", "").strip(),
        "X_ACCESS_TOKEN": os.environ.get("X_ACCESS_TOKEN", "").strip(),
        "X_ACCESS_SECRET": os.environ.get("X_ACCESS_SECRET", "").strip(),
    }
    missing = [k for k, v in env_map.items() if not v]

    if missing:
        print(f"[INFO] X APIキーが未設定のためX投稿をスキップします（未設定: {', '.join(missing)}）。")
        print("       ※ GitHub Actions 実行時はリポジトリの Secrets から自動取得されます。")
        print("       ※ ローカルPCから直接テスト投稿する場合は .env.example を参考に .env へ設定してください。")
        return None
    if tweepy is None:
        print("[WARN] tweepy が未インストールのためX投稿をスキップします (pip install -r backend/requirements.txt)。")
        return None

    return tweepy.Client(
        consumer_key=env_map["X_API_KEY"],
        consumer_secret=env_map["X_API_SECRET"],
        access_token=env_map["X_ACCESS_TOKEN"],
        access_token_secret=env_map["X_ACCESS_SECRET"],
    )


def _load_posted_history():
    raw = load_json(X_POST_HISTORY_FILE, default={"posted": []})
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        posted = raw.get("posted") or raw.get("history") or []
        return posted if isinstance(posted, list) else []
    return []


def is_already_posted(archive_id: str) -> bool:
    """同一 archiveId が既に投稿済みかどうかを判定する"""
    if not archive_id:
        return False
    return any(isinstance(entry, dict) and entry.get("archiveId") == archive_id for entry in _load_posted_history())


def record_posted_archive(archive_id: str, period: str, tweet_id: str = ""):
    """投稿完了した archiveId を履歴ファイルに記録する"""
    history = [e for e in _load_posted_history() if not (isinstance(e, dict) and e.get("archiveId") == archive_id)]
    history.insert(0, {
        "archiveId": archive_id,
        "period": period,
        "posted_at": datetime.now(JST).isoformat(timespec="seconds"),
        "tweet_id": str(tweet_id or ""),
    })
    save_json(X_POST_HISTORY_FILE, {"posted": history})


def build_tweet_text(data: dict) -> str:
    """ランキングデータから投稿用テキストを組み立てる"""
    period = data.get("period", "")
    songs = (data.get("ranking") or data.get("songs") or [])[:3]
    tweet_lines = ["🏆【週刊VOCALOID複合ランキング】", f"集計期間: {period}", ""]
    for idx, s in enumerate(songs, start=1):
        rank = s.get("rank", idx)
        combined = f"{s.get('title', '')} / {s.get('producer', '')}"
        if len(combined) > 22:
            combined = combined[:21] + "…"
        tweet_lines.append(f"{rank}位: {combined}")

    tweet_lines.extend([
        "",
        "🔽4位以降・詳細分析はこちら",
        "https://weekly-vocaloid-combined-chart.com",
        "#複合ボカラン #ボカロ #vocanew",
    ])
    return "\n".join(tweet_lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    force_post = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv
    if not PUBLIC_LATEST.exists():
        print(f"[ERROR] Ranking data not found ({PUBLIC_LATEST}). Cannot post to X.")
        return

    data = load_json(PUBLIC_LATEST)
    if not isinstance(data, dict) or not (data.get("ranking") or data.get("songs")):
        print("[ERROR] Invalid ranking data. Cannot post to X.")
        return

    archive_id, _ = infer_archive_id_and_period(data)
    if not force_post and not dry_run and not is_chart_released(data):
        print(f"[SKIP] 解禁日時前のためX投稿をスキップします ({archive_id})。")
        return

    if not force_post and not dry_run and is_already_posted(archive_id):
        print(f"[SKIP] 今週分 ({archive_id}) は既にXへ投稿済みのためスキップします。")
        return

    tweet_text = build_tweet_text(data)
    print("--- 投稿予定のテキスト ---")
    print(tweet_text)
    print("--------------------------")

    if dry_run:
        print("[DRY-RUN] テストモードのため実際のX投稿は送信しません。")
        return

    client = get_twitter_client()
    if client:
        try:
            response = client.create_tweet(text=tweet_text)
            tweet_id = ""
            resp_data = getattr(response, "data", None)
            if isinstance(resp_data, dict):
                tweet_id = resp_data.get("id", "")
            record_posted_archive(archive_id, data.get("period", ""), tweet_id=tweet_id)
            print(f"[OK] Successfully posted to X ({archive_id}): {response}")
        except Exception as e:
            print(f"[ERROR] Failed to post to X: {e}")


if __name__ == "__main__":
    main()
