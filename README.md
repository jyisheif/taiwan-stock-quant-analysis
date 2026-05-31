# 台股財報選股量化分析系統 (taiwan_stock_quant)

一個用於**台股個股財報分析、自動選股、量化分析與 AI 投資建議**的 Python 專案，
以 [Streamlit](https://streamlit.io/) 打造互動式網頁儀表板。

> ⚠️ 本專案僅供學習與研究用途，所有分析結果**不構成任何投資建議**，投資請自行評估風險。

---

## ✨ 功能特色

- **個股分析**：擷取歷史股價、計算量化指標（年化報酬、波動率、夏普比率、最大回撤、RSI）。
- **估值模型**：本益比評價法、股利折現模型（Gordon），推估合理價與折溢價。
- **自動選股**：依 ROE、本益比、EPS、負債比率等條件篩選並評分排序。
- **AI 投資建議**：整合上述資料呼叫 OpenAI 產生白話分析；無金鑰時自動改用本地規則式分析。
- **離線可用**：無網路或套件缺失時，系統會自動產生合成資料，確保介面與測試皆可運行。

---

## 📁 專案結構

```
taiwan_stock_quant/
├── streamlit_app.py        # 主程式（Streamlit 網頁介面）
├── config.py               # 全域設定（路徑、門檻、API 金鑰）
├── requirements.txt        # 套件相依清單
├── data/                   # 資料層
│   ├── __init__.py
│   ├── fetcher.py          # 資料擷取（Yahoo Finance / 合成資料）
│   ├── processor.py        # 資料清理與技術指標加工
│   └── database.py         # SQLite 資料持久化
├── analysis/               # 分析層
│   ├── __init__.py
│   ├── quant.py            # 量化績效與風險指標
│   ├── screener.py         # 條件選股與評分
│   └── valuation.py        # 估值模型
├── ai/                     # AI 層
│   ├── __init__.py
│   └── analyst.py          # LLM 投資建議（含本地備援）
├── utils/                  # 工具層
│   ├── __init__.py
│   └── helpers.py          # 共用輔助函式
├── tests/                  # 單元測試（每個模組對應一份）
│   ├── test_helpers.py
│   ├── test_data.py
│   ├── test_analysis.py
│   └── test_ai.py
└── README.md
```

---

## 🚀 安裝與執行

### 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2.（選用）設定 OpenAI 金鑰

在專案根目錄建立 `.env` 檔：

```
OPENAI_API_KEY=sk-your-key-here
```

未設定金鑰時，AI 分析會自動使用本地規則式分析。

### 3. 啟動網頁應用程式

```bash
streamlit run streamlit_app.py
```

瀏覽器開啟後即可使用「個股分析」與「自動選股」兩大功能。

---

## ✅ 執行測試

每個模組都附有對應的單元測試，可單獨或一次全部執行：

```bash
# 單獨執行某個模組測試
python tests/test_helpers.py
python tests/test_data.py
python tests/test_analysis.py
python tests/test_ai.py

# 或使用 pytest 一次執行全部
pytest -v
```

---

## 🧱 模組說明

| 模組 | 說明 |
| --- | --- |
| `config.py` | 集中管理路徑、篩選門檻、API 金鑰等設定 |
| `data/fetcher.py` | 從 Yahoo Finance 擷取股價與財報，附合成資料備援 |
| `data/processor.py` | 清理資料並計算報酬率、移動平均、波動率 |
| `data/database.py` | 以 SQLite 儲存與讀取股價、財報資料 |
| `analysis/quant.py` | 計算年化報酬、波動率、夏普比率、最大回撤、RSI |
| `analysis/screener.py` | 依財報門檻篩選並評分排序 |
| `analysis/valuation.py` | PE / 股利折現等估值模型 |
| `ai/analyst.py` | 整合資料呼叫 LLM 產生投資建議 |
| `utils/helpers.py` | 代號正規化、安全除法、數字格式化等工具 |

---

## ⚖️ 免責聲明

本系統提供之所有數據、指標與 AI 建議僅供參考與教育用途，
不保證資料正確性與即時性，亦不構成任何買賣依據。投資有風險，請審慎評估。
