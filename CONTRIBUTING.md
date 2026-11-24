# 貢獻指南

## Commit 訊息格式

本專案採用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<類型>: <標題>

- <重點 1>
- <重點 2>

Co-Authored-By: <名字> <email>   ← 選填，例如與 AI 協作時標註
```

範例：

```
feat: add moving averages to index cards

- Show 50/200/500-day moving averages under each index price
- Make the windows configurable via MA_WINDOWS
```

### 1. 類型：這次改動的性質

| 類型 | 什麼時候用 | 例子 |
|---|---|---|
| `feat` | 新功能 | 新增台股指數、新增走勢圖頁面 |
| `fix` | 修 bug | 修正週線日期標錯 |
| `perf` | 效能改善 | dashboard 加快取 |
| `refactor` | 重構，功能不變 | 把共用函式抽出來 |
| `docs` | 只改文件 | 更新 README |
| `test` | 只加或改測試 | 補 scheduler 測試 |
| `style` | 只改排版，不影響邏輯 | 縮排、空白 |
| `build` | 打包設定或套件 | 新增 Python 套件 |
| `ci` | CI/CD 設定 | GitHub Actions |
| `chore` | 其他雜項 | 更新 `.gitignore` |

可以加上範圍，例如 `feat(frontend): ...`，非必要。

### 2. 標題（第一行）

- **英文祈使句**，像在下指令：`add ...`、`fix ...`，不寫 `added`、`adds`。
- **開頭小寫、結尾不加句號**。
- **盡量 50 字元內**，整行不超過 72 字元。
- **寫「做了什麼」，不寫「改了哪個檔案」**：
  - ✅ `feat: add moving averages to index cards`
  - ❌ `update IndexCard.tsx and main.py`

### 3. 內文（與標題之間空一行）

- 用 `-` 條列，只寫重要的。
- 說明「為什麼」或「影響是什麼」；怎麼做的看程式碼就知道。
- 不列檔名，不貼程式碼裡的註解。

### 4. 破壞性改動

會讓舊用法失效的改動（例如 API 改名、移除參數），在類型後加 `!`，並在最後用 `BREAKING CHANGE:` 說明怎麼遷移：

```
feat!: rename /api/prices to /api/indices/{id}/prices

BREAKING CHANGE: 前端要改呼叫新的路徑
```

### 5. 一個 commit 只做一件事

不相關的改動分開 commit（例如「新增功能」和「修一個無關的 bug」），之後要回溯或還原比較容易。

## Commit 前的檢查

```bash
cd backend && uv run pytest          # 後端測試
cd frontend && npm run build         # 前端型別檢查 + 打包
```

不要 commit `.env` 等含密碼的檔案（已在 `.gitignore` 排除），設定範本請改 `.env.example`。
