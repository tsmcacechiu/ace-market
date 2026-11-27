# 市場溫度計

每天抓 S&P 500 / Nasdaq 100 / 費城半導體 / 台灣加權指數 / 黃金 / 比特幣的估值與技術指標，換算成歷史百分位，判斷大盤貴還是便宜。

另有「個股診斷」頁（`/stocks`）：0050、台積電、聯發科，台積電與聯發科另有證交所的本益比、股價淨值比、殖利率歷史（2005/09 起）。
設計與後續規劃見 [plan.md](plan.md)。

## 啟動

以下指令都在專案根目錄（`Market/`）執行。若已經 `cd backend`，就把 `--directory backend` 拿掉（否則會出現 `No such file or directory (os error 2)`）。

```bash
# 後端（第一次會自動建立 backend/.venv）
uv run --directory backend python -m market.jobs.daily --full    # 第一次：下載完整歷史（約 2 分鐘）
uv run --directory backend uvicorn market.api.main:app --reload  # API: http://127.0.0.1:8000/docs

# 前端（另開一個終端機）
cd frontend
npm install
npm run dev                                     # http://localhost:5173
```

## 資料庫（Supabase / 本機 SQLite）

連線設定放在 `backend/.env`（已被 `.gitignore` 排除，**不要 commit**），範本見 `backend/.env.example`：

```bash
cp backend/.env.example backend/.env   # 填入 DATABASE_URL
```

- 有設 `DATABASE_URL` → 讀寫 Supabase Postgres；沒設 → 用本機 `backend/data/market.db`（SQLite）。
- 請用 Supabase **Session pooler**（`aws-0-<region>.pooler.supabase.com:5432`，帳號是 `postgres.<project-ref>`）。Direct connection（`db.<ref>.supabase.co`）只有 IPv6，多數家用網路連不上。
- 密碼有特殊字元要 URL 編碼（`%` → `%25`、`@` → `%40`）。
- 第一次執行會自動建表；換新資料庫後跑一次 `--full` 即可補齊歷史。
- `job` 和 API 都讀同一個 `DATABASE_URL`，launchd 排程也會自動讀 `backend/.env`。

## 每天自動更新

### 方式一：API server 內建排程（預設）

`uvicorn` 啟動後會自動排程，每天 **06:30（Asia/Taipei）** 抓資料，也就是美股收盤後。
如果 server 啟動時今天的時段已經過了，而且之後都還沒跑過 job，會馬上補跑一次。

手動觸發（例如想立刻抓最新資料）：

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/run            # 增量更新
curl -X POST "http://127.0.0.1:8000/api/jobs/run?full=true"  # 重新下載完整歷史
curl http://127.0.0.1:8000/api/jobs/latest                  # 查看結果
```

如果已經有 job 在跑，會回傳 `409`。可以在 `backend/.env` 調整：

| 變數 | 預設 | 說明 |
|---|---|---|
| `SCHEDULE_ENABLED` | `1` | 設 `0` 關閉內建排程 |
| `SCHEDULE_TIME` | `06:30` | 每天執行時間（HH:MM） |
| `SCHEDULE_TZ` | `Asia/Taipei` | 時區 |

注意：只用一個 uvicorn worker 跑（`--workers` > 1 會讓每個 worker 各排一次）。

### 方式二：macOS launchd（server 沒開也會跑）

要用這個方式，請在 `.env` 設 `SCHEDULE_ENABLED=0`，避免一天跑兩次。

```bash
cp backend/scripts/com.market.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.market.daily.plist
launchctl start com.market.daily               # 立刻跑一次測試
```
每天 06:30 執行，紀錄在 `backend/data/logs/`。停用：`launchctl unload ~/Library/LaunchAgents/com.market.daily.plist`

## 部署（前後端分開）

| 環境變數 | 設在 | 說明 |
|---|---|---|
| `VITE_API_BASE` | 前端（**build 時**） | 後端網址，例如 `https://market-api.onrender.com`。本機開發不用設，Vite 會把 `/api` 轉到 `127.0.0.1:8000` |
| `CORS_ORIGINS` | 後端 | 允許呼叫 API 的前端網址，逗號分隔，例如 `https://market-web.onrender.com`。預設只允許 `localhost:5173` |
| `DATABASE_URL` | 後端 | 同上方「資料庫」一節 |

### 後端部署到 Render

設定在根目錄的 `render.yaml`（Blueprint）。第一次：

1. Render Dashboard → **New → Blueprint** → 選這個 GitHub repo → 會建立 `market-api`（新加坡、Free）。
2. 填入 `DATABASE_URL`（跟 `backend/.env` 同一條），`CORS_ORIGINS` 先留空，等前端部署後再填。
3. 部署完成後打開 `https://<服務網址>/docs` 確認。

之後 push 到 `main` 會自動重新部署。

- **Free 方案閒置 15 分鐘會休眠**，休眠時內建排程不會跑；下次有人打開網站喚醒時（約 1 分鐘），若錯過當天 06:30 會自動補跑。
- `TZ=Asia/Taipei`：job 時間以伺服器時區記錄，和本機寫入的舊資料一致。
- 本機和 Render 都開著 server 時，兩邊都會排程抓資料（結果相同，只是重複）。要避免的話，本機 `.env` 設 `SCHEDULE_ENABLED=0`。

範本見 `frontend/.env.example`、`backend/.env.example`。`VITE_API_BASE` 是在 build 時寫進前端檔案的，改了要重新 build / 重新部署前端才會生效。

## 測試

```bash
cd backend && uv run pytest
```

## 資料來源

| 資料 | 來源 |
|---|---|
| 指數價格、ETF 本益比快照 | Yahoo Finance（yfinance） |
| 個股價格（還原權息） | 2010 年起：證交所 STOCK_DAY 每日成交＋TWT49U 除權息資料；2010 年以前：Yahoo（見下方說明） |
| 個股本益比、股價淨值比、殖利率（每日） | 證交所 BWIBBU（每月一次請求，間隔 3 秒，避免被擋） |
| GDP、企業股權市值、10 年期公債殖利率 | FRED CSV（不需 API key） |
| S&P 500 本益比、席勒本益比 | multpl.com |

FRED 和 multpl 會擋一般 Python HTTP client，所以用 `curl_cffi` 模擬瀏覽器（`market/collectors/http.py`）。

- **台股假交易日**：Yahoo 對台股個股 / ETF 會在休市日（例如 2026/10/23）和暫停交易期間補一筆成交量 0、價格沿用前一天的資料，會讓均線多算天數。代號 `.TW` 的資料會剔除成交量 0 的日子（指數沒有成交量資料，不適用）。
- **個股價格（`market/tw_prices.py`）**：Yahoo 的台股個股資料有錯（0050 的 2025 年 1 拆 4 只還原到 2014 年；聯發科的配股還原日期錯），所以個股價格改用證交所的原始成交價，再依除權息參考價往回還原（還原權息）。最新一天的價格就是實際成交價。
  - 分割不在除權息表裡，要手動加進 `TW_SPLITS`。證交所標示 `**`（分割後恢復交易）的日子如果沒列在裡面，job 會失敗並提示。
  - 2010 年以前用 Yahoo 的還原股價，縮放到跟證交所的資料接得上，而且只保留最後一次「單日漲跌超過漲跌停」之後的部分（2015/6 以前是 7%，之後是 10%）。
  - 寫入前會檢查整段資料都沒有超過漲跌停的單日漲跌，有的話這一步失敗，資料庫維持原本的價格。
  - 第一次執行會從 2010/01 開始補資料，每檔約 10 分鐘。
- **新增個股**：在 `TARGETS` 加一筆 `group: "stock"`，價格會自動改從證交所抓；上市股票再加 `twse: "代號"`，會自動補證交所的估值歷史（第一次每檔約 13 分鐘）。

## 新增指標

在 `backend/market/metrics/__init__.py` 寫一個 compute 函式並加一個 `MetricDef`，
下次 job 執行後就會出現在 API 和前端表格，不用改前端。

## 可調整的設定（`backend/market/config.py`）

- `PERCENTILE_YEARS`：百分位比較的歷史長度（預設 30 年）
- `MIN_MONTHS_FOR_PERCENTILE`：資料少於幾個月不算百分位（預設 12）
- `KIND_WEIGHTS`：市場溫度中估值 / 技術指標的權重（預設 2 : 1）
- `TARGETS`：要追蹤的指數 / 個股（`group` 決定在首頁或個股診斷頁）
