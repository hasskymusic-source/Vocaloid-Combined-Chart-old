/**
 * HTTP通信（リトライ・重複抑止）および外部ライブラリ動的ローダーモジュール
 */
import { state } from "./config-state.js";

/** Chart.js ライブラリをオンデマンドで遅延ロードする */
export function ensureChartJsLoaded() {
  if (typeof Chart !== "undefined") {
    return Promise.resolve(true);
  }
  if (state.chartJsLoadingPromise) {
    return state.chartJsLoadingPromise;
  }
  state.chartJsLoadingPromise = new Promise(function (resolve) {
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";
    script.crossOrigin = "anonymous";
    script.referrerPolicy = "no-referrer";
    script.async = true;
    script.onload = function () {
      resolve(true);
    };
    script.onerror = function () {
      state.chartJsLoadingPromise = null;
      resolve(false);
    };
    document.head.appendChild(script);
  });
  return state.chartJsLoadingPromise;
}

/** 指数バックオフとランダムジッターで再試行待機する */
export function sleepWithJitter(attempt) {
  const baseDelay = 220 * Math.pow(1.8, attempt);
  const jitter = Math.floor(Math.random() * 280);
  return new Promise(function (resolve) {
    setTimeout(resolve, baseDelay + jitter);
  });
}

/** 単一URLからタイムアウト・リトライ・同一リクエスト抑止付きでJSONを取得する */
export async function fetchJsonSingleUrl(url, cacheMode, timeoutMs, maxRetries) {
  const mode = cacheMode || "no-cache";
  const timeout = timeoutMs || 6500;
  const retries = maxRetries !== undefined ? maxRetries : 2;
  const requestKey = mode + "::" + url;

  if (state.inflightJsonRequests.has(requestKey)) {
    return state.inflightJsonRequests.get(requestKey);
  }

  const task = (async function () {
    for (let attempt = 0; attempt <= retries; attempt++) {
      const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      const timerId = controller
        ? setTimeout(function () {
            controller.abort();
          }, timeout)
        : null;

      try {
        const res = await fetch(url, {
          cache: mode,
          credentials: "same-origin",
          signal: controller ? controller.signal : undefined
        });
        if (timerId) clearTimeout(timerId);

        if (res.ok) {
          return await res.json();
        }
        if (res.status >= 400 && res.status < 500 && res.status !== 429) {
          return null;
        }
      } catch (_) {
        if (timerId) clearTimeout(timerId);
      }

      if (attempt < retries) {
        await sleepWithJitter(attempt);
      }
    }
    return null;
  })();

  state.inflightJsonRequests.set(requestKey, task);
  try {
    return await task;
  } finally {
    state.inflightJsonRequests.delete(requestKey);
  }
}

/** 候補URLリストを先頭から順に試行し、最初に取得できたJSONを返す */
export async function fetchJsonWithFallback(urls, cacheMode) {
  for (let i = 0; i < urls.length; i++) {
    const data = await fetchJsonSingleUrl(urls[i], cacheMode || "no-cache");
    if (data) {
      return data;
    }
  }
  return null;
}
