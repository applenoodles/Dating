# Date Scout｜約會地點社群檢索

一個用 Streamlit 寫的「約會去哪」助手。重點是**資料檢索、消息來源、檢索日期與實用建議**，而不是讓 LLM 憑空編資料。

## 核心做法

1. **Dcard / PTT：主要內容來源**
   - 抓最新文章、內文、留言線索，附來源日期與檢索日期。
   - 適合找「新開幕、約會餐廳、情侶景點、展覽、市集、雨天備案」。
2. **IG / Threads / X：社群搜尋線索**
   - 不做登入爬蟲、不繞驗證、不碰付費牆。
   - 透過免費搜尋套件抓公開搜尋結果標題與摘要。
   - 也可以把手上的公開貼文連結貼進 App，抓公開 metadata 當來源。
3. **LLM：只負責整理與判斷，不憑空編資料**
   - 每個建議都附來源與檢索日期。
   - IG / Threads / X 若只是搜尋摘要，會標註「社群搜尋線索，需點開確認」。
4. **不使用付費檢索 API**
   - Dcard 公開可讀端點、PTT 公開 HTML、免費搜尋套件 `ddgs`。
   - LLM 可用 OpenAI-compatible API（選用）。

## 安裝與執行

```bash
cd date-scout

python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .env.example .env

streamlit run app.py
```

如果要串 LLM，把 `.env` 裡的 `LLM_API_KEY` 填上即可；不填也能跑，只是會用規則版摘要。

## 環境變數

| 變數 | 說明 |
|---|---|
| `LLM_API_KEY` | OpenAI-compatible API key，留空則使用規則版摘要 |
| `LLM_MODEL` | 模型名稱，預設 `gpt-4.1-mini` |
| `LLM_BASE_URL` | 自訂 OpenAI-compatible endpoint，留空用官方預設 |
| `SEARCH_PROVIDER_ORDER` | 搜尋後端 fallback 順序，預設 `brave,google,searxng,ddgs` |
| `BRAVE_API_KEYS` | Brave Search 金鑰，**逗號分隔可串多把**，自動輪替 |
| `GOOGLE_CSE_KEYS` | Google CSE 金鑰，逗號分隔可串多把 |
| `GOOGLE_CSE_CX` | Google 可程式化搜尋引擎 ID |
| `SEARXNG_INSTANCES` | 免金鑰 SearXNG 公開實例 URL，逗號分隔可串多個 |

## 搜尋後端（資料來源的核心）

整個 App 的「能不能無腦客製化搜尋」取決於搜尋後端。設計成**多家 provider 串成 fallback 鏈，每家內部一個金鑰池**：

- **fallback 鏈**：`brave → google → searxng → ddgs`，前一家沒額度/出錯就換下一家。
- **金鑰池輪替**：每家用逗號串多把免費金鑰，round-robin 輪替；某把吃到 `429`/額度滿就冷卻跳過下一把。
- **疊加免費額度**：例如 3 把 Brave 金鑰 ≈ 6000 次/月，再疊 Google CSE 每把 100 次/天。
- **零金鑰也能跑**：全部留空時自動只用免金鑰的 SearXNG / ddgs（較不穩）。

你只要去申請免費金鑰、貼進 `.env`，輪替與備援程式會自動處理。側欄「搜尋後端狀態」會顯示每家目前有幾把可用金鑰。

### 主要內容來源也是 query-driven

- **Dcard**：用你的城市＋偏好關鍵字打 `search/posts` 搜尋端點（搜不到才補抓各版最新文）。
- **PTT**：用各看板原生搜尋 `/bbs/{board}/search?q=`。
- **網頁/IG/Threads/X**：走上面的搜尋後端 fallback 鏈。

## 資料來源規則

| 來源 | 角色 | 新鮮度 | 可信層級 |
|---|---|---|---|
| Dcard | 主要內容來源 | 高，可抓最新文章 | 已讀內文 |
| PTT | 主要內容來源 | 高，可抓最新看板文章 | 已讀內文 |
| 免費網頁搜尋 | 補充來源、找社群線索 | 中，不保證即時 | 搜尋摘要線索 |
| IG / Threads / X 搜尋結果 | 社群風向線索 | 中低，需點開確認 | 搜尋摘要線索 |
| 手動貼上的社群連結 | 你看到的貼文補強 | 取決於貼文 | 連結預覽 |

## 設計準則

1. 沒有 LLM API key 也能跑。
2. 任一來源失敗不會讓整個 App 掛掉。
3. 每個推薦都有來源與檢索日期。
4. 社群搜尋摘要標示為「需點開確認」。
5. 不顯示裸 URL，來源一律用 Markdown 連結呈現。
