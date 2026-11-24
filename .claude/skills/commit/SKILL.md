---
name: commit
description: 在本專案 commit 變更：跑檢查、挑檔案、拆成單一主題的 commit，並照 CONTRIBUTING.md 寫訊息。使用者說 commit、寫 commit、提交、commit + push 時使用。
---

# Commit（本專案）

訊息格式的唯一來源是根目錄的 [`CONTRIBUTING.md`](../../../CONTRIBUTING.md)，寫訊息前先讀它。這份 skill 只管流程。

## 步驟

### 1. 盤點變更

```bash
git status --short
git diff --stat
```

完成條件：每個變更檔都歸到一個**主題**（一個功能、一個修正、一份文件……），並且知道哪些是這次工作改的。不是這次工作改的檔案，列給使用者看，由他決定要不要納入。

### 2. 跑檢查

依變更範圍跑對應的檢查，全部通過（綠）才往下：

| 改到 | 指令 |
|---|---|
| `backend/` | `uv run --directory backend pytest -q` |
| `frontend/` | `cd frontend && npm run build`（型別檢查 + 打包，部署用的就是這個） |

檢查失敗（紅）就停下，把錯誤輸出告訴使用者，不 commit。

### 3. 每個主題一個 commit

依步驟 1 的主題，逐一 `git add <檔案>` 指名加入，一次只放一個主題的檔案。同一個檔案混了兩個主題時，可以拆成兩個 commit，或在 commit 內文裡把兩件事都寫清楚，由你判斷哪個比較清楚。

完成條件：`git diff --staged --stat` 列出的檔案剛好就是這個主題的檔案。

**機密檔案**：`.env`（例如 `backend/.env` 裡有 Supabase 密碼）只能留在本機。設定要分享時，改 `.env.example`。

### 4. 寫訊息並 commit

照 `CONTRIBUTING.md` 寫訊息。本 repo 的歷史慣例是**不加範圍**（`feat: ...`，不是 `feat(api): ...`），標題用英文。

本機是 macOS 內建的 bash 3.2，`$(cat <<'EOF' ... EOF)` 會出錯。訊息請從 stdin 傳入：

```bash
git commit -F - <<'EOF'
feat: add moving averages to index cards

- Show 50/200/500-day moving averages under each index price
EOF
```

有多個主題就回到步驟 3，直到 `git status` 只剩使用者決定不納入的檔案。

### 5. Push（只在使用者要求時）

使用者有說 push 才執行 `git push origin main`，並用 `git status -sb` 確認已經和 `origin/main` 同步。

### 6. 回報

列出每個 commit 的 hash 和標題、檢查結果，以及是否已 push。還沒 commit 的檔案也要列出來。
