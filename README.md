# 市場溫度計

每天抓 S&P 500 / Nasdaq 100 / 費城半導體的估值與技術指標，換算成歷史百分位，判斷大盤貴還是便宜。
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

## 測試

```bash
cd backend && uv run pytest
```

## 資料來源

| 資料 | 來源 |
|---|---|
| 指數價格、ETF 本益比快照 | Yahoo Finance（yfinance） |
| GDP、企業股權市值、10 年期公債殖利率 | FRED CSV（不需 API key） |
| S&P 500 本益比、席勒本益比 | multpl.com |

FRED 和 multpl 會擋一般 Python HTTP client，所以用 `curl_cffi` 模擬瀏覽器（`market/collectors/http.py`）。

## 新增指標

在 `backend/market/metrics/__init__.py` 寫一個 compute 函式並加一個 `MetricDef`，
下次 job 執行後就會出現在 API 和前端表格，不用改前端。

## 可調整的設定（`backend/market/config.py`）

- `PERCENTILE_YEARS`：百分位比較的歷史長度（預設 30 年）
- `MIN_MONTHS_FOR_PERCENTILE`：資料少於幾個月不算百分位（預設 12）
- `KIND_WEIGHTS`：市場溫度中估值 / 技術指標的權重（預設 2 : 1）
- `TARGETS`：要追蹤的指數與對應 ETF
