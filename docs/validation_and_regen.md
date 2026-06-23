# 關卡生成的「驗證 + 自動重生」機制

## 流程（streamlit_app.py `_do_generate`，最多重試 2 次）

```
for attempt in 1..2:
  1. 呼叫 Gemini 生成（串流；思考 / JSON 分流顯示）
  2. extract_json_from_response(answer)  → level_dict
        失敗(None) ─→ (A) 沒解析出 JSON
                       → 把「請只輸出一個完整 ```json 區塊」回饋給模型 → 重生
  3. validate_level(level_dict)  → ValidationResult(valid, errors[], warnings[])
        valid=False ─→ (B) 驗證不過
                       → 逐條 emit 印出 errors
                       → 把 errors 塞回 prompt（「上次這些問題請修正」）→ 重生
        valid=True  ─→ break，關卡就緒
```

- 用完 2 次仍失敗：(A) 顯示「請再按一次」；(B) 仍讓玩家玩，但提示可能有瑕疵。
- **不需要額外 subagent**：同一個模型重生、把錯誤塞進 prompt 即可，省時間省 token。

## 驗證 agent（`validator.validate_level`）輸出什麼

`ValidationResult`：
- `valid: bool` — 是否通過（有任何 error 就 False）
- `errors: list[str]` — **致命**問題（缺欄位、行列數不符、tile_id 不存在…）→ 會觸發重生
- `warnings: list[str]` — **非致命**提醒（盤面偏小、max_steps 偏高、goal 找不到對應物件…）→ 不擋遊玩

## 為什麼之前的 JSON 不通過 — 實測例子

### 例子 A：模型碎念 / JSON 被截斷（解析階段就失敗）
輸入（截圖那種「等一下，Row 3 拼寫…」碎念 + 半截 JSON）：
```
等一下，Row 3 的拼寫 "Crt1"，我剛剛草稿差點寫錯。
```json
{ "rows": 8, "cols": 8, "max_steps": 20, "board": [["Red","Grn",
```
- `extract_json_from_response` → **None**（沒有閉合的完整 JSON）
- 之前會直接報「❌ 沒有回傳有效 JSON」；**現在**：(A) 自動重生，並要求「只輸出完整 ```json 區塊」。
- 另外已修：① 思考 / 答案分流可能把 JSON 切壞 → 現在思考裡的 JSON 也撈得回來；② `extract_json` 改用「平衡括號」掃描 → JSON 後面接「### 設計說明」也能正確解析。

### 例子 B：JSON 合法但行列數不符 / 缺欄位（驗證階段失敗）
輸入：
```json
{ "rows": 8, "cols": 8, "max_steps": 20,
  "board": [["Red","Grn","Blu"], ["Red","Grn"]],
  "goals": {"Crt1": 4} }
```
`validate_level` 輸出：
```
valid = False
errors:
  • board 行數 2 與 rows=8 不符
  • board[0] 列數 3 與 cols=8 不符
  • board[1] 列數 2 與 cols=8 不符
warnings:
  • goal "Crt1" 在盤面上找不到對應物件（若盤面為隨機生成則忽略此警告）
```
→ 逐條印在 Agent Pipeline 執行紀錄，並把這些 errors 回饋給模型自動重生。

### 例子 C：缺 max_steps（最常見）
```json
{ "rows": 8, "cols": 8, "board": [...], "goals": {"Crt1": 4} }
```
→ `errors: ["缺少必填欄位: max_steps"]` → 重生。

## 重現方式
```bash
python -c "from level_generator.validator import validate_level; \
print(validate_level({'rows':8,'cols':8,'max_steps':20,'board':[['Red']],'goals':{'Crt1':4}}).errors)"
```
