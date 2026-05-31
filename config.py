# -*- coding: utf-8 -*-
"""
config.py
全域設定檔：集中管理專案中所有可調整的參數、路徑與機密金鑰。
其他模組透過 `from config import settings` 取得設定，避免硬編碼（hard-code）。
"""

import os                                          # 匯入 os 模組，用於讀取環境變數與處理檔案路徑
from pathlib import Path                           # 匯入 Path，用物件導向方式處理跨平台路徑
from dataclasses import dataclass, field           # 匯入 dataclass，用簡潔語法定義設定資料類別

try:                                               # 嘗試載入 .env 檔（若使用者有安裝 python-dotenv）
    from dotenv import load_dotenv                 # 匯入 load_dotenv 函式
    load_dotenv()                                  # 將專案根目錄的 .env 內容載入到環境變數
except ImportError:                                # 若未安裝 python-dotenv 則略過（不影響執行）
    pass                                           # 不做任何事，使用系統既有的環境變數

# ===== 路徑設定 =====
BASE_DIR = Path(__file__).resolve().parent         # 取得本檔案所在資料夾，作為專案根目錄
DATA_DIR = BASE_DIR / "data_store"                 # 定義資料儲存資料夾（存放下載的快取與資料庫）
DATA_DIR.mkdir(exist_ok=True)                      # 若該資料夾不存在則自動建立


@dataclass                                         # 使用 dataclass 裝飾器自動產生 __init__ 等方法
class Settings:                                    # 定義設定類別，集中存放所有參數
    """專案全域設定容器。"""                        # 類別說明文字

    # --- 資料庫設定 ---
    db_path: str = str(DATA_DIR / "stock.db")      # SQLite 資料庫檔案的完整路徑

    # --- 資料來源設定 ---
    data_source: str = "yfinance"                  # 主要資料來源（可選 'yfinance' 或 'twstock'）
    market_suffix: str = ".TW"                     # 台股在 Yahoo Finance 的代號後綴（上市為 .TW）
    otc_suffix: str = ".TWO"                       # 上櫃股票在 Yahoo Finance 的代號後綴
    default_period: str = "1y"                     # 預設擷取的歷史股價區間（1 年）
    default_interval: str = "1d"                   # 預設股價資料頻率（1d 日線、1wk 週線、1mo 月線）
    request_timeout: int = 15                      # 對外請求的逾時秒數，避免程式卡住
    max_retries: int = 2                           # 對外請求失敗時的重試次數

    # --- 財報擷取設定 ---
    statement_max_periods: int = 4                 # 財報最多保留的期數（例如近 4 季或近 4 年）
    translate_to_chinese: bool = True              # 是否將財報欄位自動翻譯為中文
    fiscal_currency: str = "TWD"                   # 財報幣別標示（台股為新台幣）

    # --- 量化分析預設參數 ---
    risk_free_rate: float = 0.015                  # 無風險利率（用於計算夏普比率），預設 1.5%
    trading_days: int = 252                        # 一年的交易日數（年化計算用）

    # --- 選股篩選預設門檻 ---
    min_roe: float = 0.10                          # 股東權益報酬率（ROE）最低門檻，預設 10%
    max_pe: float = 20.0                           # 本益比（PE）上限，預設 20 倍
    min_eps: float = 1.0                           # 每股盈餘（EPS）最低門檻，預設 1 元
    max_debt_ratio: float = 0.6                    # 負債比率上限，預設 60%

    # --- AI 設定 ---
    openai_api_key: str = field(                   # OpenAI API 金鑰，從環境變數讀取以保護機密
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    openai_model: str = "gpt-4o-mini"              # 預設使用的 OpenAI 模型名稱

    # --- 一般設定 ---
    cache_ttl: int = 3600                          # 快取存活時間（秒），預設 1 小時


settings = Settings()                              # 建立一個全域設定實例，供其他模組直接匯入使用


if __name__ == "__main__":                         # 當此檔案被直接執行（而非被匯入）時
    # 印出目前設定，方便快速檢查設定是否正確
    print("=== 台股量化分析系統設定 ===")            # 標題
    print(f"專案根目錄: {BASE_DIR}")                # 顯示專案根目錄
    print(f"資料庫路徑: {settings.db_path}")        # 顯示資料庫路徑
    print(f"ROE 門檻: {settings.min_roe:.0%}")     # 以百分比顯示 ROE 門檻
    print(f"OpenAI 金鑰已設定: {bool(settings.openai_api_key)}")  # 顯示是否已設定金鑰
