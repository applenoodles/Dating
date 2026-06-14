# 任務交接：Date Scout（接續強化）

接手者請先讀這份，再動手。所有東西都在分支 `claude/照内容评估实作-mvgv47`，
程式在 `date-scout/`。最新 commit：`0016e8d`，已 push。

---

## 0. 30 秒啟動（網頁圖形介面，不是純 CLI）

```powershell
cd "D:\vibe code\dating\date-scout"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

瀏覽器自動開 **http://localhost:8501**：左欄填城市/天數/資料源，中間填偏好，
按「開始檢索」就出附來源與檢索日期的報告，可下載 Markdown。
**不填任何金鑰也能跑**（PTT + 免費 ddgs + 規則版報告）。

金鑰（全部選配）放在 `date-scout/.env`（已從 `.env.example` 建好）：
- `BRAVE_API_KEYS`：https://brave.com/search/api/ （最推薦先弄，網頁搜尋會穩很多）
- `GOOGLE_CSE_KEYS` + `GOOGLE_CSE_CX`：https://programmablesearchengine.google.com/
- `THREADS_API_KEY`：https://scrapecreators.com/ （開啟 Threads 即時搜尋）
- `LLM_API_KEY`（+ 選填 `LLM_BASE_URL`/`LLM_MODEL`）：OpenAI 相容端點，留空用規則版
改完 `.env` 要**重啟** App 才會生效（金鑰只在啟動時讀）。

---

## 1. 已完成且在真實網路實測過

- **SSL/連線韌性**：`app.py` 開頭 `truststore.inject_into_ssl()`，讓 httpx 走 OS 憑證庫
  （本機在企業 SSL 檢查代理後面才連得出去）；`http_get_with_retry()` 對逾時/429/5xx 退避重試。
- **Dcard 優雅降級**：API/HTML 皆被 Cloudflare 擋（見 §3），撞 403 即短路、只記一筆提示，
  Dcard 內容改由網頁搜尋的 `site:www.dcard.tw` 帶出。`_dcard_posts()` 會正規化回傳形狀。
- **PTT**：主要直讀來源，實測「台北」166 筆候選、日期解析正確。
- **搜尋後端**：無金鑰時掉到 ddgs 可正常回；`provider_status()` 正確；零結果且只有免金鑰
  備援時會補友善提示。
- **Threads（選用、key-gated）**：`collect_threads()` 接 ScrapeCreators
  `GET /v1/threads/search`（`x-api-key`），新增 `social_post` 層級「社群貼文（建議點開原文）」。
  沒設 `THREADS_API_KEY` 自動略過。映射/防呆/key-gating 已用合成資料驗證。
- **報告**：`fallback_report` 四區塊齊、0 裸 URL；`build_llm_report` 系統提示禁止編造。
- **bug 修復**：`collect_seed_urls` 標題運算子優先序（og:title 但無 `<title>` 會拿到空標題）。
- Streamlit 啟動 `/_stcore/health` 回 200。

## 2. 驗收標準（務必維持）

1. 沒有任何金鑰也能跑（搜尋掉到 ddgs、LLM 用規則版）。
2. 任一來源/金鑰失敗只記進 notes，不讓 App 掛掉。
3. 每個推薦都有來源連結與檢索日期。
4. IG/Threads/X 搜尋摘要標「需點開確認」；Threads API 內文標「社群貼文（建議點開原文）」。
5. 不顯示裸 URL，一律 Markdown 連結。LLM 不得編造店名/地址/價格/營業時間/展期。

## 3. 本機環境限制（重要，會影響你怎麼測）

- **SSL 檢查 MITM 代理**：Python 的 `certifi` 不認得代理自簽 CA。
  - pip 要加 `--trusted-host pypi.org --trusted-host files.pythonhosted.org`。
  - 執行期靠內建 `truststore`（已處理）。`curl`（git-bash）會 SSL 失敗，連線探測請用 PowerShell。
- **沒裝 Docker**：`docker compose up` 無法在本機實測，只能靜態檢查 compose/Dockerfile。
- **Dcard 全擋**：`/service/api` 與 HTML 皆回 Cloudflare 403（IP/TLS 指紋硬擋），
  非 header 能解；這是設計上接受的現實，靠 `site:www.dcard.tw` 補。

## 4. 尚未驗證（需金鑰或對應環境才能測）

- **Threads live 抓取**：本機無 `THREADS_API_KEY`，沒做真實呼叫。填 key 後第一次跑會驗證
  欄位映射；若 ScrapeCreators 改欄位名，會表現為 Threads 結果偏少/為 0，再對照修 `threads_post_to_item()`。
- **Docker 一鍵啟動**：本機無 Docker。
- **`build_llm_report` 對真 LLM**：本機無 LLM key，未跑 end-to-end。

## 5. Backlog（依價值排序，皆為選配加強）

1. **Apify Threads 映射**：`collect_threads` 已留擴充點；給定 actor id 與其 output 欄位即可加
   `*_post_to_item` 映射（Apify 有同步的 `run-sync-get-dataset-items`）。RapidAPI 各家欄位不一，未內建。
2. **SQLite 存每日結果**：做「近 7 天變熱門」趨勢。
3. **約會情境篩選**：第一次/曖昧/紀念日/雨天/低預算/捷運可達。
4. **來源可信度排序**：依平台層級/互動數加權。

## 6. 工作方式

- 小步改、每個可驗證改動就 commit（訊息寫清楚做了什麼、怎麼驗的），push 到
  `claude/照内容评估实作-mvgv47`，**不要碰 main**。
- 會動到架構或可能違反驗收標準的決定，先問人再做。
- ToS 提醒：以「跨家疊加免費額度」為主；不做登入爬蟲、不繞驗證、不偷 cookie。
