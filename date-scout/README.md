# Date Scout｜約會地點社群檢索

一個用 Streamlit 寫的「約會去哪」助手。重點是**資料檢索、消息來源、檢索日期與實用建議**，而不是讓 LLM 憑空編資料。

## 核心做法

1. **PTT：主要直讀內容來源**
   - 用各看板原生搜尋 `/bbs/{board}/search` 抓最新文章、內文、留言線索，附來源日期與檢索日期。
   - 適合找「新開幕、約會餐廳、情侶景點、展覽、市集、雨天備案」。
2. **Dcard：主要靠網頁搜尋帶出（直連常被擋）**
   - Dcard 伺服器端常被 Cloudflare 擋下（資料中心 IP / 非瀏覽器 TLS 指紋會直接吃 403），
     直連 `/service/api` 進不去；因此 Dcard 內容**主要靠網頁搜尋的 `site:www.dcard.tw` 帶出**。
   - 直連 collector 仍保留：在沒被擋的網路下能直接讀文章與留言；被擋時會優雅降級（只記一筆狀態、不會卡住）。
3. **IG / Threads / X：社群搜尋線索**
   - 不做登入爬蟲、不繞驗證、不碰付費牆。
   - 透過免費搜尋套件抓公開搜尋結果標題與摘要。
   - 也可以把手上的公開貼文連結貼進 App，抓公開 metadata 當來源。
   - **Threads 即時搜尋（選用、需金鑰）**：設定 `THREADS_API_KEY` 後，會額外用關鍵字打
     非官方 Threads 搜尋 API（預設 ScrapeCreators）抓公開貼文內文與讚／回數，標為
     「社群貼文（建議點開原文）」。我們只當 API 客戶端、不自行登入；沒設金鑰就自動略過。
4. **LLM：只負責整理與判斷，不憑空編資料**
   - 每個建議都附來源與檢索日期。
   - IG / Threads / X 若只是搜尋摘要，會標註「社群搜尋線索，需點開確認」。
5. **不使用付費檢索 API**
   - PTT 公開 HTML、Dcard 公開端點（可達時）、免費搜尋後端（Brave / Google CSE / SearXNG / `ddgs`）。
   - LLM 可用 OpenAI-compatible API（選用）。

## 怎麼 pull 下來用

先把專案抓下來、切到分支、進到 `date-scout` 資料夾：

```bash
git clone https://github.com/applenoodles/dating.git
cd dating
git checkout claude/照内容评估实作-mvgv47
cd date-scout

cp .env.example .env      # 之後把申請到的金鑰填進 .env
```

接著二選一跑起來。**不一定要 Docker**，本機 Python 就能完整跑。

### 方法 A：本機 Python（推薦，不需 Docker）

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

開瀏覽器到 **http://localhost:8501** 就能用了。沒填任何金鑰也能跑（搜尋掉到免金鑰 ddgs、LLM 用規則版摘要）。

> **企業/校園網路要注意**：若你的網路有 SSL 檢查代理（自簽根憑證），Python 的 `httpx` 預設會
> 因為憑證驗證失敗而連不出去。本專案已內建 `truststore`，會自動改走作業系統的憑證信任庫解決這點；
> 在乾淨環境或 Docker 內它等同預設行為，不影響正常驗證。

### 方法 B：Docker（選用，要打包部署再用）

需要先裝 Docker Desktop（Win/Mac）或 Docker Engine（Linux）。

```bash
# 只跑 App（規則版摘要，不用任何金鑰也能跑）
docker compose up -d --build
```

一樣開 **http://localhost:8501**。停掉：`docker compose down`。

### 開始用

1. 左側欄填城市/區域、調整天數，展開「搜尋後端狀態」確認有幾把金鑰可用。
2. 中間填你的偏好（例如「想要有吃有玩、第一次約會、不要太貴、要有雨天備案」）。
3. 有看到的 IG/Threads/X 公開貼文連結可貼進「手動補充」框。
4. 按「開始檢索」，下面就會出報告，可直接下載 Markdown。

> 不填任何金鑰也能跑：搜尋會掉到免金鑰的 ddgs/SearXNG（較不穩），LLM 會改用規則版摘要。要穩、要好，就去申請免費金鑰填進 `.env`。

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
| `THREADS_API_KEY` | 選用。非官方 Threads 搜尋 API 金鑰（預設 ScrapeCreators），留空則整個 Threads 來源自動略過 |
| `THREADS_API_PROVIDER` | Threads 來源供應商，預設 `scrapecreators` |

## 搜尋後端（資料來源的核心）

整個 App 的「能不能無腦客製化搜尋」取決於搜尋後端。設計成**多家 provider 串成 fallback 鏈，每家內部一個金鑰池**：

- **fallback 鏈**：`brave → google → searxng → ddgs`，前一家沒額度/出錯就換下一家。
- **金鑰池輪替**：每家用逗號串多把免費金鑰，round-robin 輪替；某把吃到 `429`/額度滿就冷卻跳過下一把。
- **疊加免費額度**：例如 3 把 Brave 金鑰 ≈ 6000 次/月，再疊 Google CSE 每把 100 次/天。
- **零金鑰也能跑**：全部留空時自動只用免金鑰的 SearXNG / ddgs（較不穩）。

你只要去申請免費金鑰、貼進 `.env`，輪替與備援程式會自動處理。側欄「搜尋後端狀態」會顯示每家目前有幾把可用金鑰。

### LLM 金鑰也用金鑰池（選用）

搜尋金鑰由 `search.py` 內建輪替；LLM 金鑰則建議外包給成熟的開源閘道 **LiteLLM**，一樣是「申請完貼上就跑」。已整合進主 `docker-compose.yml`（`llm` profile）：

```bash
cp litellm.config.example.yaml litellm.config.yaml   # 視需要調整 model_list
# .env 填金鑰並設：
#   OPENAI_KEY_1=...  OPENAI_KEY_2=...  GROQ_KEY=...  LITELLM_MASTER_KEY=sk-local-master
#   LLM_BASE_URL=http://litellm:4000/v1
#   LLM_API_KEY=sk-local-master
docker compose --profile llm up -d --build
```

`litellm.config.yaml` 裡同一個 `model_name` 放多個 deployment，LiteLLM 就會自動在多把金鑰間負載平衡、失敗重試、冷卻 —— 之後申請到新金鑰只要加一行再重啟即可。

> 容器內 App 連閘道用服務名 `http://litellm:4000/v1`；若你是本機 Python（方法 B）跑 App、只用 Docker 跑閘道，則改成 `http://localhost:4000/v1`，並把 compose 裡 litellm 的 `expose` 換成 `ports: ["4000:4000"]`。

> 想要有 Web UI 管理一堆金鑰的，也可以改用 `songquanpeng/one-api`，同樣吐 OpenAI 相容端點，把 `LLM_BASE_URL` 指過去即可。

### 主要內容來源也是 query-driven

- **PTT**：用各看板原生搜尋 `/bbs/{board}/search?q=`（帶 `over18` cookie），實測穩定可讀內文與留言。
- **Dcard**：用你的城市＋偏好關鍵字打 `search/posts` 搜尋端點（搜不到才補抓各版最新文）。
  伺服器端常被 Cloudflare 擋（403）；被擋時自動降級，Dcard 內容改由下方網頁搜尋的 `site:www.dcard.tw` 帶出。
- **網頁/IG/Threads/X**：走上面的搜尋後端 fallback 鏈（含 `site:www.dcard.tw`、`site:threads.net` 等定向查詢）。

## 資料來源規則

| 來源 | 角色 | 新鮮度 | 可信層級 |
|---|---|---|---|
| PTT | 主要直讀內容來源 | 高，可抓最新看板文章 | 已讀內文 |
| Dcard（直連可達時） | 內容來源 | 高，可抓最新文章 | 已讀內文 |
| Dcard（被 Cloudflare 擋時） | 改由 `site:www.dcard.tw` 網頁搜尋帶出 | 中，不保證即時 | 搜尋摘要線索 |
| 免費網頁搜尋 | 補充來源、找社群線索 | 中，不保證即時 | 搜尋摘要線索 |
| IG / Threads / X 搜尋結果 | 社群風向線索 | 中低，需點開確認 | 搜尋摘要線索 |
| Threads API（設了金鑰時） | 社群即時內文 | 高，可帶時間範圍 | 社群貼文（建議點開原文） |
| 手動貼上的社群連結 | 你看到的貼文補強 | 取決於貼文 | 連結預覽 |

## 設計準則

1. 沒有 LLM API key 也能跑。
2. 任一來源失敗不會讓整個 App 掛掉。
3. 每個推薦都有來源與檢索日期。
4. 社群搜尋摘要標示為「需點開確認」。
5. 不顯示裸 URL，來源一律用 Markdown 連結呈現。
