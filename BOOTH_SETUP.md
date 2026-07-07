# Booth 本地架設(備援方案 — 給同事在自己電腦跑)

攤位生成器 = 一支 FastAPI 伺服器(`booth/server.py`),**同一支就同時 serve 前端 + Godot 遊戲**,不需要另外 build Godot。

## 需要拿到的東西
1. 這個 repo(整包,含 `godot_demo/web/` 已匯出的遊戲)。
2. **Vertex AI 服務帳戶金鑰 JSON**(向 owner 索取,例如 `hip-caster-*.json`)。
   - 這個檔**不在 git 裡**(已 gitignore),要另外傳。
   - 收到後放到**專案根目錄**即可(跟 `run_booth.ps1` 同一層)。

## 安裝

### macOS / Linux(同事)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 啟動

### macOS / Linux（同事）
```bash
chmod +x run_booth.sh        # 只需第一次
./run_booth.sh --port 8501   # 或任何埠口
```

### Windows
```powershell
.\run_booth.ps1 -Port 8501
```

- 兩支腳本都會**自動**在根目錄找那個服務帳戶 JSON、設好 Vertex AI 認證,再啟動。
- 打開 `http://localhost:8501/` 就是攤位生成器（Godot 遊戲由同一支伺服器 serve 在 `/game/`，不必另外裝 Godot）。
- 停止:視窗按 `Ctrl+C`。重跑同一條指令 = 安全重啟(會先清掉佔用該埠的舊 process)。
- macOS 若清埠口失敗:確認有 `lsof`（系統內建）；或手動 `lsof -ti tcp:8501 | xargs kill -9`。

## 常見問題
- **生成失敗 / 認證錯誤**:確認 JSON 有放在根目錄、且是 `type: service_account`。
- **埠口被占**:`run_booth.ps1` 會自動清掉佔用該埠的舊 process 再啟動。
- **要換模型**:`.\run_booth.ps1 -Port 8501 -Model gemini-2.5-pro`。

> 正式對外(match3.gamaniaocc.org)目前是 owner 本機的 8501 經 Cloudflare tunnel 出去;
> 此備援方案是讓同事能在**自己機器**獨立跑一份,不依賴 owner 的機器。
