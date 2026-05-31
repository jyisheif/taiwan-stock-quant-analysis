# -*- coding: utf-8 -*-
"""
data/fetcher.py
資料擷取模組：負責從外部來源（Yahoo Finance / twstock）下載台股資料，包含：
  1. 個股基本資料（公司名稱、產業、市值等）
  2. 歷史股價（開高低收量）
  3. 三大財務報表（損益表、資產負債表、現金流量表），支援季報與年報
  4. 將英文欄位／科目自動翻譯為中文

設計重點：
  - 以 pandas 為核心資料結構，方便後續分析與顯示。
  - 對外請求皆有重試與例外保護；失敗時自動退回「合成資料」，確保系統與測試可離線運行。
  - 翻譯對照表以模組層級常數維護，方便擴充新科目。
"""

from __future__ import annotations                        # 啟用延遲型別評估，讓型別註記更彈性

import os                                                 # 匯入 os，用於處理檔案路徑
import sys                                                # 匯入 sys，用於調整模組搜尋路徑
import time                                               # 匯入 time，用於重試之間的等待
from typing import Optional, Dict, Any, List             # 匯入型別註記工具

import numpy as np                                        # 匯入 numpy 做數值運算（產生合成資料用）
import pandas as pd                                       # 匯入 pandas 處理表格資料

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入路徑以匯入同層套件

from config import settings                               # 匯入全域設定（後綴、逾時、期數等）
from utils.helpers import normalize_ticker                # 匯入代號正規化工具

try:                                                      # 嘗試匯入 yfinance（可能未安裝或無網路）
    import yfinance as yf                                 # 匯入 yfinance 函式庫
    _YF_AVAILABLE = True                                  # 標記 yfinance 可用
except ImportError:                                       # 若匯入失敗
    _YF_AVAILABLE = False                                 # 標記 yfinance 不可用，後續改用合成資料

try:                                                      # 嘗試匯入 twstock（台股專用資料來源，選用）
    import twstock                                        # 匯入 twstock 函式庫
    _TWSTOCK_AVAILABLE = True                             # 標記 twstock 可用
except ImportError:                                       # 若未安裝
    _TWSTOCK_AVAILABLE = False                            # 標記 twstock 不可用


# --- 台股代號對中文名稱（內建常見權值股；未涵蓋者再由 twstock 補齊）---
TW_NAME_MAP: Dict[str, str] = {                           # 代號 -> 公司中文名稱
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電",
    "2303": "聯電", "2412": "中華電", "2882": "國泰金", "2603": "長榮",
    "2881": "富邦金", "2891": "中信金", "2884": "玉山金", "2886": "兆豐金",
    "2892": "第一金", "2880": "華南金", "2885": "元大金", "2883": "開發金",
    "2002": "中鋼", "1301": "台塑", "1303": "南亞", "1326": "台化",
    "1101": "台泥", "1216": "統一", "2207": "和泰車", "2105": "正新",
    "2382": "廣達", "2357": "華碩", "2395": "研華", "3711": "日月光投控",
    "2409": "友達", "3034": "聯詠", "2379": "瑞昱", "2327": "國巨",
    "2474": "可成", "3008": "大立光", "2912": "統一超",
    "2615": "萬海", "2609": "陽明", "2618": "長榮航",
    "2610": "華航", "2376": "技嘉", "2353": "宏碁", "2356": "英業達",
    "6505": "台塑化", "3045": "台灣大", "4904": "遠傳", "5871": "中租-KY",
    "2890": "永豐金", "2887": "台新金", "2888": "新光金", "9904": "寶成",
}


def chinese_name(code: str, fallback: str = None) -> str:  # 取得台股中文名稱
    """
    依股票代號回傳公司中文名稱：
      1. 先查內建對照表 TW_NAME_MAP；
      2. 若有安裝 twstock，再查 twstock 的完整上市櫃清單；
      3. 都查不到時回傳 fallback（或代號本身）。
    """
    code = str(code).strip()                              # 正規化代號字串
    if code in TW_NAME_MAP:                               # 先查內建對照表
        return TW_NAME_MAP[code]                          # 命中即回傳中文名
    if _TWSTOCK_AVAILABLE:                                # 若 twstock 可用
        try:                                              # 保護性查詢
            info = twstock.codes.get(code)                # 查 twstock 代號表
            if info is not None and getattr(info, "name", None):  # 若查到且有名稱
                return info.name                          # 回傳 twstock 提供的中文名
        except Exception:                                 # 任意例外
            pass                                          # 忽略，改用後備值
    return fallback or code                               # 後備：原名稱或代號


# =====================================================================
# 中英欄位對照表（翻譯用）
# 這些對照表以模組層級常數維護，新增科目時只需在此擴充即可，符合可擴展原則。
# =====================================================================

# --- 個股基本資料欄位對照（yfinance info 的 key -> 中文）---
INFO_FIELD_MAP: Dict[str, str] = {                        # 基本資料英文鍵對中文名稱
    "symbol": "股票代號",                                 # 股票代號
    "shortName": "簡稱",                                  # 公司簡稱
    "longName": "公司全名",                               # 公司全名
    "sector": "類股",                                     # 類股別
    "industry": "產業",                                   # 細產業
    "fullTimeEmployees": "員工人數",                      # 員工人數
    "country": "國家",                                    # 國家
    "city": "城市",                                       # 城市
    "website": "官方網站",                                # 公司網站
    "currency": "計價幣別",                               # 幣別
    "marketCap": "市值",                                  # 市值
    "currentPrice": "目前股價",                           # 目前股價
    "previousClose": "前一日收盤",                        # 前收盤
    "open": "開盤價",                                     # 開盤價
    "dayHigh": "當日最高",                                # 當日最高
    "dayLow": "當日最低",                                 # 當日最低
    "fiftyTwoWeekHigh": "52週最高",                       # 52 週最高
    "fiftyTwoWeekLow": "52週最低",                        # 52 週最低
    "volume": "成交量",                                   # 成交量
    "trailingPE": "本益比",                               # 本益比
    "forwardPE": "預估本益比",                            # 預估本益比
    "priceToBook": "股價淨值比",                          # 股價淨值比
    "trailingEps": "每股盈餘",                            # 每股盈餘
    "returnOnEquity": "股東權益報酬率",                   # ROE
    "returnOnAssets": "資產報酬率",                       # ROA
    "dividendYield": "殖利率",                            # 殖利率
    "dividendRate": "現金股利",                           # 現金股利
    "debtToEquity": "負債權益比",                         # 負債權益比
    "profitMargins": "淨利率",                            # 淨利率
    "grossMargins": "毛利率",                             # 毛利率
    "operatingMargins": "營業利益率",                     # 營業利益率
    "beta": "Beta係數",                                   # Beta 係數
    "longBusinessSummary": "公司簡介",                    # 公司簡介
}

# --- 損益表科目對照（yfinance 列名 -> 中文）---
INCOME_STMT_MAP: Dict[str, str] = {                       # 損益表英文科目對中文
    "Total Revenue": "營業收入",                          # 營業收入
    "Operating Revenue": "營業收入(營運)",                # 營運收入
    "Cost Of Revenue": "營業成本",                        # 營業成本
    "Gross Profit": "營業毛利",                           # 毛利
    "Operating Expense": "營業費用",                      # 營業費用
    "Research And Development": "研發費用",               # 研發費用
    "Selling General And Administration": "管銷費用",     # 管理及銷售費用
    "Operating Income": "營業利益",                       # 營業利益
    "Total Operating Income As Reported": "營業利益(申報)",  # 申報營業利益
    "Net Non Operating Interest Income Expense": "業外利息淨額",  # 業外利息淨額
    "Other Income Expense": "其他收入支出",               # 其他收支
    "Pretax Income": "稅前淨利",                          # 稅前淨利
    "Tax Provision": "所得稅費用",                        # 所得稅費用
    "Net Income": "稅後淨利",                             # 稅後淨利
    "Net Income Common Stockholders": "歸屬母公司淨利",   # 歸屬母公司淨利
    "Net Income Continuous Operations": "繼續營業淨利",   # 繼續營業單位淨利
    "Basic EPS": "基本每股盈餘",                          # 基本 EPS
    "Diluted EPS": "稀釋每股盈餘",                        # 稀釋 EPS
    "Basic Average Shares": "加權平均股數",               # 加權平均股數
    "Diluted Average Shares": "稀釋加權平均股數",         # 稀釋加權平均股數
    "EBIT": "息前稅前利益",                               # EBIT
    "EBITDA": "稅前息前折舊攤銷前利益",                   # EBITDA
    "Interest Expense": "利息支出",                       # 利息支出
    "Interest Income": "利息收入",                        # 利息收入
    "Total Expenses": "總費用",                           # 總費用
}

# --- 資產負債表科目對照（yfinance 列名 -> 中文）---
BALANCE_SHEET_MAP: Dict[str, str] = {                     # 資產負債表英文科目對中文
    "Total Assets": "資產總額",                           # 資產總額
    "Current Assets": "流動資產",                         # 流動資產
    "Cash And Cash Equivalents": "現金及約當現金",        # 現金及約當現金
    "Cash Cash Equivalents And Short Term Investments": "現金及短期投資",  # 現金及短期投資
    "Other Short Term Investments": "其他短期投資",       # 其他短期投資
    "Receivables": "應收款項",                            # 應收款項
    "Accounts Receivable": "應收帳款",                    # 應收帳款
    "Inventory": "存貨",                                  # 存貨
    "Other Current Assets": "其他流動資產",               # 其他流動資產
    "Total Non Current Assets": "非流動資產",             # 非流動資產
    "Net PPE": "不動產廠房設備淨額",                      # 不動產廠房及設備淨額
    "Gross PPE": "不動產廠房設備總額",                    # 不動產廠房及設備總額
    "Total Liabilities Net Minority Interest": "負債總額",  # 負債總額
    "Current Liabilities": "流動負債",                    # 流動負債
    "Accounts Payable": "應付帳款",                       # 應付帳款
    "Payables And Accrued Expenses": "應付款項及費用",    # 應付款項及應計費用
    "Current Debt": "短期借款",                           # 短期借款
    "Total Non Current Liabilities Net Minority Interest": "非流動負債",  # 非流動負債
    "Long Term Debt": "長期借款",                         # 長期借款
    "Total Debt": "總負債(含借款)",                       # 總借款
    "Net Debt": "淨負債",                                 # 淨負債
    "Total Equity Gross Minority Interest": "權益總額",   # 權益總額
    "Stockholders Equity": "股東權益",                    # 股東權益
    "Common Stock Equity": "普通股權益",                  # 普通股權益
    "Retained Earnings": "保留盈餘",                      # 保留盈餘
    "Capital Stock": "股本",                              # 股本
    "Common Stock": "普通股股本",                         # 普通股股本
    "Working Capital": "營運資金",                        # 營運資金
    "Tangible Book Value": "有形淨值",                    # 有形淨值
    "Share Issued": "已發行股數",                         # 已發行股數
    "Ordinary Shares Number": "普通股股數",               # 普通股股數
}

# --- 現金流量表科目對照（yfinance 列名 -> 中文）---
CASHFLOW_MAP: Dict[str, str] = {                          # 現金流量表英文科目對中文
    "Operating Cash Flow": "營業活動現金流",              # 營業活動現金流
    "Investing Cash Flow": "投資活動現金流",              # 投資活動現金流
    "Financing Cash Flow": "籌資活動現金流",              # 籌資活動現金流
    "Free Cash Flow": "自由現金流",                       # 自由現金流
    "Capital Expenditure": "資本支出",                    # 資本支出
    "Changes In Cash": "現金淨變動",                      # 現金淨變動
    "Beginning Cash Position": "期初現金",                # 期初現金餘額
    "End Cash Position": "期末現金",                      # 期末現金餘額
    "Depreciation And Amortization": "折舊及攤銷",        # 折舊及攤銷
    "Change In Working Capital": "營運資金變動",          # 營運資金變動
    "Net Income From Continuing Operations": "繼續營業淨利",  # 繼續營業淨利
    "Issuance Of Debt": "舉借債務",                       # 舉借新債
    "Repayment Of Debt": "償還債務",                      # 償還債務
    "Issuance Of Capital Stock": "發行股票",              # 發行股票
    "Repurchase Of Capital Stock": "買回庫藏股",          # 買回庫藏股
    "Cash Dividends Paid": "支付現金股利",                # 現金股利支出
    "Interest Paid Supplemental Data": "支付利息",        # 支付利息
    "Income Tax Paid Supplemental Data": "支付所得稅",    # 支付所得稅
}


class StockFetcher:                                        # 定義股票資料擷取類別
    """
    台股資料擷取器：對外提供基本資料、歷史股價與三大財報的擷取介面。
    所有方法在來源不可用時都會自動退回合成資料，確保呼叫端不會中斷。
    """

    def __init__(self, suffix: str = None):               # 建構子，可指定市場後綴
        self.suffix = suffix or settings.market_suffix    # 若未指定則使用設定檔的預設後綴（.TW）
        self.timeout = settings.request_timeout           # 從設定取得請求逾時秒數
        self.max_retries = settings.max_retries           # 從設定取得失敗重試次數

    # ------------------------------------------------------------------
    # 內部工具方法
    # ------------------------------------------------------------------

    def _get_ticker(self, code: str):                     # 取得 yfinance Ticker 物件
        """以正規化後的代號建立並回傳 yfinance Ticker 物件。"""  # 方法說明
        ticker = normalize_ticker(code, self.suffix)      # 將代號正規化為 Yahoo 格式（2330.TW）
        return yf.Ticker(ticker)                          # 回傳對應的 Ticker 物件

    def _retry(self, func, *args, **kwargs):              # 通用重試包裝器
        """
        執行 func 並在失敗時依設定重試；全部失敗則回傳 None。
        將重試邏輯集中於此，避免在各方法重複撰寫。
        """
        last_err = None                                   # 記錄最後一次的錯誤
        for attempt in range(self.max_retries + 1):       # 嘗試「初次 + 重試次數」次
            try:                                          # 嘗試執行目標函式
                return func(*args, **kwargs)              # 成功則直接回傳結果
            except Exception as exc:                      # 若發生例外
                last_err = exc                            # 保存錯誤
                time.sleep(0.5 * (attempt + 1))           # 採漸進式等待後再重試
        return None                                       # 全部失敗回傳 None（呼叫端再決定備援）

    @staticmethod                                          # 靜態方法，不需實例狀態
    def _translate_index(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
        """
        將財報 DataFrame 的列索引（科目名稱）依對照表翻譯為中文。
        對照表中找不到的科目維持原文，確保不遺漏任何資料。
        """
        if df is None or df.empty:                        # 若資料為空
            return df                                     # 原樣回傳
        if not settings.translate_to_chinese:             # 若設定關閉翻譯
            return df                                     # 不翻譯直接回傳
        df = df.copy()                                    # 複製避免改到原始資料
        df.index = [mapping.get(str(idx), str(idx)) for idx in df.index]  # 逐列翻譯，找不到則保留原文
        return df                                         # 回傳翻譯後的資料

    @staticmethod                                          # 靜態方法
    def _format_period_columns(df: pd.DataFrame, max_periods: int) -> pd.DataFrame:
        """
        將財報欄位（期間日期）格式化為 'YYYY-MM-DD' 字串，並只保留最近 max_periods 期。
        """
        if df is None or df.empty:                        # 若資料為空
            return pd.DataFrame()                         # 回傳空表
        df = df.copy()                                    # 複製資料
        df = df.iloc[:, :max_periods]                     # 只保留最近的數期（yfinance 由新到舊排列）
        new_cols = []                                     # 用於收集格式化後的欄位名稱
        for col in df.columns:                            # 逐一處理每個期間欄位
            try:                                          # 嘗試將欄位轉為日期字串
                new_cols.append(pd.to_datetime(col).strftime("%Y-%m-%d"))  # 格式化為日期字串
            except Exception:                             # 若無法轉換（非日期）
                new_cols.append(str(col))                 # 維持原字串
        df.columns = new_cols                             # 套用新的欄位名稱
        return df                                         # 回傳整理後的財報

    # ------------------------------------------------------------------
    # 1. 個股基本資料
    # ------------------------------------------------------------------

    def get_stock_info(self, code: str) -> Dict[str, Any]:    # 取得個股基本資料
        """
        取得個股基本資料（公司名稱、產業、市值、估值指標等），鍵名為中文。
        來源不可用時回傳合成的基本資料。
        """
        if not _YF_AVAILABLE:                             # 若 yfinance 不可用
            return self.generate_sample_info(code)        # 回傳合成基本資料

        info = self._retry(lambda: self._get_ticker(code).info)  # 帶重試地取得 info 字典
        if not info or len(info) < 3:                     # 若取得失敗或內容過少
            return self.generate_sample_info(code)        # 退回合成資料

        result: Dict[str, Any] = {"原始代號": str(code)}   # 結果字典，先放入使用者輸入的代號
        for en_key, zh_key in INFO_FIELD_MAP.items():     # 依對照表逐欄翻譯
            if en_key in info and info[en_key] is not None:  # 若該欄位存在且有值
                result[zh_key] = info[en_key]             # 以中文鍵名存入結果
        return result                                     # 回傳中文化的基本資料

    # ------------------------------------------------------------------
    # 2. 歷史股價
    # ------------------------------------------------------------------

    def fetch_price_history(                               # 擷取歷史股價的方法
        self,
        code: str,                                        # 股票代號（例如 '2330'）
        period: str = None,                               # 擷取區間（例如 '1y'、'6mo'）
        interval: str = None,                             # 資料頻率（例如 '1d'、'1wk'）
        source: str = None,                               # 指定資料來源（'yfinance'/'twstock'）
    ) -> pd.DataFrame:                                    # 回傳值為含 OHLCV 的 DataFrame
        """
        下載指定股票的歷史股價（開高低收與成交量）。
        依 source（或設定的預設來源）選擇 yfinance 或 twstock；
        任一來源不可用或失敗時，皆退回合成資料以維持系統可運作。
        """
        period = period or settings.default_period        # 若未指定區間則使用預設值
        interval = interval or settings.default_interval  # 若未指定頻率則使用預設值
        source = source or settings.data_source           # 若未指定來源則使用設定的預設來源

        if source == "twstock" and _TWSTOCK_AVAILABLE:    # 若指定 twstock 且該套件可用
            df = self._fetch_price_twstock(code, period)  # 改用 twstock 擷取
            if df is not None and not df.empty:           # 若成功取得資料
                return df                                 # 直接回傳
            # twstock 失敗時繼續嘗試 yfinance 作為備援

        if not _YF_AVAILABLE:                             # 若 yfinance 不可用
            return self.generate_sample_price(code)       # 直接回傳合成資料

        df = self._retry(                                 # 帶重試地下載歷史資料
            lambda: self._get_ticker(code).history(period=period, interval=interval)
        )
        if df is None or df.empty:                        # 若下載失敗或結果為空
            return self.generate_sample_price(code)       # 退而求其次回傳合成資料

        df = df.reset_index()                             # 將日期索引轉為一般欄位
        df.columns = [str(c).lower() for c in df.columns]  # 欄位名稱統一轉小寫，方便後續處理
        if "datetime" in df.columns and "date" not in df.columns:  # 分鐘/週線索引名稱可能為 datetime
            df = df.rename(columns={"datetime": "date"})  # 統一改名為 date
        return df                                         # 回傳整理後的 DataFrame

    @staticmethod                                          # 靜態方法
    def _period_to_months(period: str) -> int:           # 將區間字串換算為月數
        """將 yfinance 風格的區間字串（如 '6mo'、'1y'）換算為月數。"""  # 方法說明
        period = str(period).strip().lower()             # 正規化字串
        try:                                             # 嘗試解析數字部分
            if period.endswith("mo"):                    # 若以 'mo' 結尾（月）
                return max(1, int(period[:-2]))          # 取月數
            if period.endswith("y"):                     # 若以 'y' 結尾（年）
                return max(1, int(period[:-1]) * 12)     # 年轉月
        except ValueError:                               # 解析失敗時
            pass                                         # 落到預設值
        return 12                                        # 預設回傳 12 個月

    def _fetch_price_twstock(self, code: str, period: str) -> Optional[pd.DataFrame]:
        """
        使用 twstock 擷取台股歷史日線資料，並整理為與 yfinance 一致的欄位格式。
        twstock 僅支援台股且速度較慢，作為 yfinance 之外的第二來源。
        """
        try:                                              # 包覆於 try 以防 twstock 內部例外
            pure_code = str(code).split(".")[0].strip()   # 取出純數字代號（去掉 .TW 後綴）
            stock = twstock.Stock(pure_code)              # 建立 twstock Stock 物件
            months = self._period_to_months(period)       # 將區間換算為月數
            start = pd.Timestamp.today() - pd.DateOffset(months=months)  # 計算起始日期
            # fetch_from 會抓取指定年月至今的所有日線資料
            records = self._retry(lambda: stock.fetch_from(start.year, start.month))  # 帶重試擷取
            if not records:                               # 若無資料
                return None                               # 回傳 None 讓上層改用備援
            df = pd.DataFrame([{                          # 將每筆紀錄轉為標準欄位
                "date": r.date,                           # 日期
                "open": r.open,                           # 開盤價
                "high": r.high,                           # 最高價
                "low": r.low,                             # 最低價
                "close": r.close,                         # 收盤價
                "volume": r.capacity,                     # 成交量（成交股數）
            } for r in records])
            df["date"] = pd.to_datetime(df["date"])       # 將日期欄位轉為 datetime
            return df.sort_values("date").reset_index(drop=True)  # 依日期排序後回傳
        except Exception:                                 # 任何例外
            return None                                   # 回傳 None，由呼叫端決定備援

    # ------------------------------------------------------------------
    # 3. 三大財務報表（季報 / 年報）
    # ------------------------------------------------------------------

    def get_income_statement(self, code: str, quarterly: bool = False) -> pd.DataFrame:
        """
        取得損益表。quarterly=True 取季報，False 取年報；科目名稱翻為中文。
        """
        return self._fetch_statement(code, "income", quarterly, INCOME_STMT_MAP)  # 委派給通用方法

    def get_balance_sheet(self, code: str, quarterly: bool = False) -> pd.DataFrame:
        """
        取得資產負債表。quarterly=True 取季報，False 取年報；科目名稱翻為中文。
        """
        return self._fetch_statement(code, "balance", quarterly, BALANCE_SHEET_MAP)  # 委派給通用方法

    def get_cash_flow(self, code: str, quarterly: bool = False) -> pd.DataFrame:
        """
        取得現金流量表。quarterly=True 取季報，False 取年報；科目名稱翻為中文。
        """
        return self._fetch_statement(code, "cashflow", quarterly, CASHFLOW_MAP)  # 委派給通用方法

    def get_financial_statements(                         # 一次取得三大報表
        self,
        code: str,                                        # 股票代號
        quarterly: bool = False,                          # 是否取季報
    ) -> Dict[str, pd.DataFrame]:
        """
        一次取得損益表、資產負債表與現金流量表，回傳以中文為鍵的字典。
        方便上層（如 AI 分析或網頁）一次取用全部報表。
        """
        return {                                          # 組裝三大報表字典
            "損益表": self.get_income_statement(code, quarterly),     # 損益表
            "資產負債表": self.get_balance_sheet(code, quarterly),     # 資產負債表
            "現金流量表": self.get_cash_flow(code, quarterly),         # 現金流量表
        }

    def _fetch_statement(                                 # 取得財報的通用內部方法
        self,
        code: str,                                        # 股票代號
        kind: str,                                        # 報表種類（income/balance/cashflow）
        quarterly: bool,                                  # 是否取季報
        mapping: Dict[str, str],                          # 對應的中文翻譯表
    ) -> pd.DataFrame:
        """
        擷取指定種類的財報並完成翻譯與格式化。
        將三種報表共用的流程集中於此，符合 DRY 原則、便於維護擴充。
        """
        if not _YF_AVAILABLE:                             # 若 yfinance 不可用
            return self.generate_sample_statement(code, kind, quarterly)  # 回傳合成報表

        tk = self._get_ticker(code)                       # 建立 Ticker 物件
        # 依報表種類與頻率，對應到 yfinance 的屬性名稱
        attr_map = {                                      # 種類對 yfinance 屬性的對照
            ("income", False): "income_stmt",             # 年度損益表
            ("income", True): "quarterly_income_stmt",    # 季度損益表
            ("balance", False): "balance_sheet",          # 年度資產負債表
            ("balance", True): "quarterly_balance_sheet", # 季度資產負債表
            ("cashflow", False): "cashflow",              # 年度現金流量表
            ("cashflow", True): "quarterly_cashflow",     # 季度現金流量表
        }
        attr = attr_map.get((kind, quarterly))            # 取得對應屬性名稱
        df = self._retry(lambda: getattr(tk, attr))       # 帶重試地取得該報表
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:  # 若取得失敗或為空
            return self.generate_sample_statement(code, kind, quarterly)  # 退回合成報表

        df = self._format_period_columns(df, settings.statement_max_periods)  # 格式化期間欄位
        df = self._translate_index(df, mapping)           # 將科目翻譯為中文
        return df                                         # 回傳整理後的財報

    # ------------------------------------------------------------------
    # 4. 關鍵財報指標（向後相容既有介面）
    # ------------------------------------------------------------------

    def fetch_financials(self, code: str) -> Dict[str, Any]:   # 擷取基本面財報指標的方法
        """
        擷取個股的關鍵財報指標（本益比、ROE、EPS、市值等），供選股與估值使用。
        鍵名沿用英文以維持與分析模組相容；無法取得時回傳合成資料。
        """
        if not _YF_AVAILABLE:                             # 若 yfinance 不可用
            return self.generate_sample_financials(code)  # 回傳合成財報資料

        info = self._retry(lambda: self._get_ticker(code).info)  # 帶重試地取得 info
        if not info or len(info) < 3:                     # 若資訊太少（代表抓取失敗）
            return self.generate_sample_financials(code)  # 回傳合成資料
        return {                                          # 擷取需要的欄位並標準化為自訂格式
            "code": str(code),                            # 股票代號
            "name": chinese_name(code, info.get("shortName", code)),  # 公司中文名稱（查無則用原始簡稱）
            "pe": info.get("trailingPE"),                 # 本益比（PE）
            "pb": info.get("priceToBook"),                # 股價淨值比（PB）
            "eps": info.get("trailingEps"),               # 每股盈餘（EPS）
            "roe": info.get("returnOnEquity"),            # 股東權益報酬率（ROE）
            "dividend_yield": info.get("dividendYield"),  # 殖利率
            "debt_ratio": info.get("debtToEquity"),       # 負債權益比
            "market_cap": info.get("marketCap"),          # 市值
            "price": info.get("currentPrice"),            # 目前股價
        }

    # ==================================================================
    # 合成（模擬）資料產生器：供離線測試與無網路情境使用
    # ==================================================================

    def _rng(self, code: str, salt: int = 0):             # 建立可重現的亂數產生器
        """以股票代號（加上鹽值）為種子建立亂數產生器，確保結果可重現。"""  # 方法說明
        seed = (abs(hash(str(code))) + salt) % (2**32)    # 由代號計算亂數種子
        return np.random.default_rng(seed)                # 回傳亂數產生器

    def generate_sample_price(self, code: str, days: int = 252) -> pd.DataFrame:
        """產生一段合成的歷史股價資料（隨機漫步模型），用於離線測試或示範。"""  # 方法說明
        rng = self._rng(code)                             # 以代號為種子建立亂數產生器
        dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="B")  # 產生 days 個營業日
        returns = rng.normal(0.0005, 0.02, days)          # 產生每日報酬率（平均略正、波動 2%）
        price = 100 * np.cumprod(1 + returns)             # 以 100 為基準累乘得到價格序列
        close = np.round(price, 2)                        # 收盤價取兩位小數
        df = pd.DataFrame({                               # 組裝成 DataFrame
            "date": dates,                                # 日期欄位
            "open": np.round(close * (1 + rng.normal(0, 0.005, days)), 2),   # 開盤價
            "high": np.round(close * (1 + np.abs(rng.normal(0, 0.01, days))), 2),  # 最高價
            "low": np.round(close * (1 - np.abs(rng.normal(0, 0.01, days))), 2),   # 最低價
            "close": close,                               # 收盤價
            "volume": rng.integers(1000, 50000, days) * 1000,  # 成交量
        })
        return df                                         # 回傳合成股價資料

    def generate_sample_financials(self, code: str) -> Dict[str, Any]:
        """產生一組合成的財報指標資料，數值落在合理範圍內。"""  # 方法說明
        rng = self._rng(code)                             # 以代號為種子，確保同一代號結果一致
        return {                                          # 回傳合成財報字典
            "code": str(code),                            # 股票代號
            "name": chinese_name(code, f"範例公司{code}"),  # 公司中文名稱（查無則用合成名稱）
            "pe": round(float(rng.uniform(8, 30)), 2),    # 本益比介於 8~30
            "pb": round(float(rng.uniform(0.8, 5)), 2),   # 股價淨值比介於 0.8~5
            "eps": round(float(rng.uniform(0.5, 15)), 2), # 每股盈餘介於 0.5~15
            "roe": round(float(rng.uniform(0.03, 0.30)), 4),  # ROE 介於 3%~30%
            "dividend_yield": round(float(rng.uniform(0, 0.06)), 4),  # 殖利率 0%~6%
            "debt_ratio": round(float(rng.uniform(0.2, 0.8)), 4),  # 負債比率 20%~80%
            "market_cap": int(rng.integers(1_000, 500_000)) * 1_000_000,  # 市值
            "price": round(float(rng.uniform(20, 600)), 2),  # 股價介於 20~600
        }

    def generate_sample_info(self, code: str) -> Dict[str, Any]:
        """產生合成的個股基本資料（中文鍵名），用於離線測試或示範。"""  # 方法說明
        rng = self._rng(code, salt=7)                     # 以代號加鹽值建立亂數產生器
        sectors = ["半導體", "電子零組件", "金融保險", "航運", "傳產製造"]  # 類股清單
        return {                                          # 回傳合成基本資料（中文鍵）
            "原始代號": str(code),                        # 使用者輸入的代號
            "股票代號": f"{code}{self.suffix}",           # 含後綴的完整代號
            "簡稱": f"範例公司{code}",                    # 公司簡稱
            "公司全名": f"範例股份有限公司{code}",        # 公司全名
            "類股": sectors[int(rng.integers(0, len(sectors)))],  # 隨機指派類股
            "產業": "範例產業",                           # 產業
            "市值": int(rng.integers(1_000, 500_000)) * 1_000_000,  # 市值
            "目前股價": round(float(rng.uniform(20, 600)), 2),  # 目前股價
            "本益比": round(float(rng.uniform(8, 30)), 2),  # 本益比
            "股東權益報酬率": round(float(rng.uniform(0.03, 0.30)), 4),  # ROE
            "計價幣別": settings.fiscal_currency,         # 幣別
        }

    def generate_sample_statement(                        # 產生合成的三大報表之一
        self,
        code: str,                                        # 股票代號
        kind: str,                                        # 報表種類（income/balance/cashflow）
        quarterly: bool = False,                          # 是否為季報
    ) -> pd.DataFrame:
        """
        依報表種類產生一份合成財報（中文科目、近數期），供離線測試或示範。
        數值僅為示意，會維持基本的會計關係（例如毛利 = 收入 - 成本）。
        """
        rng = self._rng(code, salt=hash(kind) % 1000)     # 以代號與種類建立亂數產生器
        periods = settings.statement_max_periods          # 取得要產生的期數
        # 依季報或年報建立期間欄位（由新到舊）
        freq = "QE" if quarterly else "YE"                # 季報用季底、年報用年底
        cols = (                                          # 產生期間欄位並格式化為日期字串
            pd.date_range(end=pd.Timestamp.today(), periods=periods, freq=freq)
            .strftime("%Y-%m-%d")[::-1]                   # 反轉成由新到舊，符合 yfinance 慣例
            .tolist()
        )

        def series(low: float, high: float) -> List[float]:   # 產生一列隨機數值的小工具
            """產生 periods 個介於 low~high 的隨機整數（以千元為單位）。"""  # 函式說明
            return [int(rng.uniform(low, high)) * 1000 for _ in range(periods)]  # 回傳隨機數列

        if kind == "income":                              # 若為損益表
            revenue = series(5_000_000, 20_000_000)       # 營業收入
            cost = [int(r * rng.uniform(0.5, 0.7)) for r in revenue]  # 營業成本（佔收入 50~70%）
            gross = [r - c for r, c in zip(revenue, cost)]  # 毛利 = 收入 - 成本
            op_income = [int(g * rng.uniform(0.4, 0.8)) for g in gross]  # 營業利益
            net_income = [int(o * rng.uniform(0.6, 0.95)) for o in op_income]  # 稅後淨利
            data = {                                      # 組裝損益表（中文科目）
                "營業收入": revenue,                      # 營業收入
                "營業成本": cost,                         # 營業成本
                "營業毛利": gross,                        # 毛利
                "營業利益": op_income,                    # 營業利益
                "稅後淨利": net_income,                   # 稅後淨利
                "基本每股盈餘": [round(n / 1e8, 2) for n in net_income],  # 以淨利推估 EPS（示意）
            }
        elif kind == "balance":                           # 若為資產負債表
            assets = series(50_000_000, 200_000_000)      # 資產總額
            liabilities = [int(a * rng.uniform(0.3, 0.6)) for a in assets]  # 負債總額（30~60%）
            equity = [a - l for a, l in zip(assets, liabilities)]  # 權益 = 資產 - 負債
            data = {                                      # 組裝資產負債表（中文科目）
                "資產總額": assets,                       # 資產總額
                "流動資產": [int(a * rng.uniform(0.3, 0.5)) for a in assets],  # 流動資產
                "負債總額": liabilities,                  # 負債總額
                "流動負債": [int(l * rng.uniform(0.4, 0.7)) for l in liabilities],  # 流動負債
                "股東權益": equity,                       # 股東權益
                "保留盈餘": [int(e * rng.uniform(0.3, 0.6)) for e in equity],  # 保留盈餘
            }
        else:                                             # 否則為現金流量表
            op_cf = series(3_000_000, 12_000_000)         # 營業活動現金流（正值）
            inv_cf = [-int(o * rng.uniform(0.3, 0.7)) for o in op_cf]  # 投資活動現金流（多為負）
            fin_cf = [-int(o * rng.uniform(0.1, 0.4)) for o in op_cf]  # 籌資活動現金流（多為負）
            data = {                                      # 組裝現金流量表（中文科目）
                "營業活動現金流": op_cf,                  # 營業活動現金流
                "投資活動現金流": inv_cf,                 # 投資活動現金流
                "籌資活動現金流": fin_cf,                 # 籌資活動現金流
                "自由現金流": [o + i for o, i in zip(op_cf, inv_cf)],  # 自由現金流 = 營業 + 投資
                "現金淨變動": [o + i + f for o, i, f in zip(op_cf, inv_cf, fin_cf)],  # 現金淨變動
            }

        return pd.DataFrame(data, index=cols).T           # 以期間為欄、科目為列回傳（與 yfinance 一致）


if __name__ == "__main__":                                # 直接執行此檔的簡易示範
    fetcher = StockFetcher()                              # 建立擷取器
    print("=== 基本資料 ===")                             # 標題
    for k, v in fetcher.generate_sample_info("2330").items():  # 逐項印出合成基本資料
        print(f"{k}: {v}")                                # 印出鍵與值
    print("\n=== 合成損益表（年報）===")                  # 標題
    print(fetcher.generate_sample_statement("2330", "income", quarterly=False))  # 印出合成損益表
    print("\n=== 合成現金流量表（季報）===")              # 標題
    print(fetcher.generate_sample_statement("2330", "cashflow", quarterly=True))  # 印出合成現金流量表
