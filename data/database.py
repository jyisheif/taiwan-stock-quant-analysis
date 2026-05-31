# -*- coding: utf-8 -*-
"""
data/database.py
資料庫模組：使用 Python 內建的 sqlite3 將股價與財報資料持久化儲存，
提供建立資料表、寫入、讀取等基本操作，作為本地快取以減少重複下載。
"""

from __future__ import annotations                        # 啟用延遲型別評估

import os                                                 # 匯入 os，用於處理路徑
import sys                                                # 匯入 sys，用於調整模組搜尋路徑
import sqlite3                                            # 匯入內建的 SQLite 資料庫介面
from datetime import datetime                             # 匯入 datetime，用於記錄快取時間
from typing import Optional, Dict, Any                    # 匯入型別註記工具

import pandas as pd                                       # 匯入 pandas 處理表格資料

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

from config import settings                               # 匯入全域設定以取得資料庫路徑


class StockDatabase:                                       # 定義資料庫操作類別
    """封裝 SQLite 連線與股票資料讀寫的類別。"""           # 類別說明

    def __init__(self, db_path: str = None):              # 建構子，可指定資料庫檔路徑
        self.db_path = db_path or settings.db_path        # 未指定時使用設定檔的預設路徑
        self._init_tables()                               # 初始化所需的資料表

    def _connect(self) -> sqlite3.Connection:             # 建立資料庫連線的私有方法
        """建立並回傳一個 SQLite 連線物件。"""             # 方法說明
        return sqlite3.connect(self.db_path)              # 連線到指定的資料庫檔（不存在則自動建立）

    def _init_tables(self) -> None:                       # 初始化資料表
        """若資料表不存在則建立股價表與財報表。"""          # 方法說明
        with self._connect() as conn:                     # 使用 with 確保連線正確關閉
            cur = conn.cursor()                           # 取得游標以執行 SQL
            cur.execute(                                  # 建立股價歷史資料表
                """
                CREATE TABLE IF NOT EXISTS price_history (
                    code   TEXT,                          -- 股票代號
                    date   TEXT,                          -- 交易日期
                    open   REAL,                          -- 開盤價
                    high   REAL,                          -- 最高價
                    low    REAL,                          -- 最低價
                    close  REAL,                          -- 收盤價
                    volume INTEGER,                       -- 成交量
                    PRIMARY KEY (code, date)              -- 以代號加日期為主鍵，避免重複
                )
                """
            )
            cur.execute(                                  # 建立財報資料表
                """
                CREATE TABLE IF NOT EXISTS financials (
                    code           TEXT PRIMARY KEY,      -- 股票代號（主鍵）
                    name           TEXT,                  -- 公司名稱
                    pe             REAL,                  -- 本益比
                    pb             REAL,                  -- 股價淨值比
                    eps            REAL,                  -- 每股盈餘
                    roe            REAL,                  -- 股東權益報酬率
                    dividend_yield REAL,                  -- 殖利率
                    debt_ratio     REAL,                  -- 負債比率
                    market_cap     INTEGER,               -- 市值
                    price          REAL                   -- 目前股價
                )
                """
            )
            cur.execute(                                  # 建立財務報表快取資料表
                """
                CREATE TABLE IF NOT EXISTS financial_statements (
                    code           TEXT,                  -- 股票代號
                    statement_type TEXT,                  -- 報表種類（損益表/資產負債表/現金流量表）
                    freq           TEXT,                  -- 週期（Y 年報 / Q 季報）
                    item           TEXT,                  -- 會計科目（中文）
                    period         TEXT,                  -- 期間（YYYY-MM-DD）
                    value          REAL,                  -- 數值
                    seq            INTEGER,               -- 科目原始排序（保留報表的科目順序）
                    updated_at     TEXT,                  -- 快取寫入時間
                    PRIMARY KEY (code, statement_type, freq, item, period)  -- 複合主鍵避免重複
                )
                """
            )
            conn.commit()                                 # 提交變更，使資料表建立生效

    def save_price_history(self, code: str, df: pd.DataFrame) -> int:  # 寫入股價資料
        """
        將某股票的歷史股價寫入資料庫（已存在的同日資料會被覆蓋）。
        回傳寫入的資料筆數。
        """
        if df is None or df.empty:                        # 若無資料
            return 0                                       # 不寫入並回傳 0
        out = df.copy()                                   # 複製避免改到原始資料
        out.columns = [str(c).lower() for c in out.columns]  # 欄位轉小寫以對齊資料表
        keep = ["date", "open", "high", "low", "close", "volume"]  # 要保留的欄位清單
        out = out[[c for c in keep if c in out.columns]]  # 只取存在且需要的欄位
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")  # 日期統一格式化為字串
        out.insert(0, "code", str(code))                  # 在最前面插入股票代號欄位
        with self._connect() as conn:                     # 建立連線
            cur = conn.cursor()                           # 取得游標
            rows = out.to_records(index=False)            # 將 DataFrame 轉為列紀錄以利批次寫入
            cur.executemany(                              # 使用 INSERT OR REPLACE 批次寫入
                """
                INSERT OR REPLACE INTO price_history
                (code, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                list(map(tuple, rows)),                   # 將紀錄轉為 tuple 清單
            )
            conn.commit()                                 # 提交寫入
            return len(out)                               # 回傳寫入筆數

    def load_price_history(self, code: str) -> pd.DataFrame:  # 讀取股價資料
        """
        從資料庫讀取指定股票的歷史股價，依日期排序後回傳 DataFrame。
        """
        with self._connect() as conn:                     # 建立連線
            df = pd.read_sql_query(                       # 以 SQL 查詢結果直接轉為 DataFrame
                "SELECT * FROM price_history WHERE code = ? ORDER BY date",
                conn,                                     # 傳入連線物件
                params=(str(code),),                      # 查詢參數（防止 SQL 注入）
            )
        return df                                         # 回傳查詢結果

    def save_financials(self, financials: Dict[str, Any]) -> None:  # 寫入財報資料
        """
        將單一股票的財報指標寫入（或更新）資料庫。
        """
        keys = ["code", "name", "pe", "pb", "eps", "roe",  # 定義欄位順序
                "dividend_yield", "debt_ratio", "market_cap", "price"]
        values = [financials.get(k) for k in keys]        # 依欄位順序取值（缺值為 None）
        with self._connect() as conn:                     # 建立連線
            cur = conn.cursor()                           # 取得游標
            cur.execute(                                  # 使用 INSERT OR REPLACE 寫入或更新
                f"""
                INSERT OR REPLACE INTO financials
                ({", ".join(keys)})
                VALUES ({", ".join(["?"] * len(keys))})
                """,
                values,                                   # 傳入對應的值
            )
            conn.commit()                                 # 提交寫入

    def load_financials(self, code: str) -> Optional[Dict[str, Any]]:  # 讀取財報資料
        """
        讀取指定股票的財報指標，若不存在則回傳 None。
        """
        with self._connect() as conn:                     # 建立連線
            conn.row_factory = sqlite3.Row                # 設定讓查詢結果可用欄位名稱存取
            cur = conn.cursor()                           # 取得游標
            cur.execute("SELECT * FROM financials WHERE code = ?", (str(code),))  # 查詢指定代號
            row = cur.fetchone()                          # 取一筆結果
        return dict(row) if row else None                 # 有資料則轉為字典回傳，否則回傳 None

    # ==================================================================
    # 三大財務報表快取（將 fetcher 取得的報表存入 / 讀出本地 SQLite）
    # ==================================================================

    def save_statements(                                  # 寫入三大報表快取
        self,
        code: str,                                        # 股票代號
        statements: Dict[str, pd.DataFrame],              # 報表字典（鍵為中文報表名）
        quarterly: bool = False,                          # 是否為季報
    ) -> int:
        """
        將三大報表（損益表/資產負債表/現金流量表）以「長格式」寫入快取。
        每個儲存格拆成一列（科目 x 期間 = 一筆值），方便日後重建與查詢。
        回傳實際寫入的儲存格筆數。
        """
        freq = "Q" if quarterly else "Y"                  # 將布林週期轉為代碼
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 取得目前時間作為快取時間戳
        rows = []                                         # 收集所有待寫入的列
        for stmt_type, df in statements.items():          # 逐一處理每份報表
            if df is None or df.empty:                    # 若報表為空
                continue                                  # 略過
            items = list(df.index)                        # 取得科目清單（保留順序）
            periods = list(df.columns)                    # 取得期間清單
            for i, item in enumerate(items):              # 逐科目（i 作為排序序號，以位置存取）
                for j, period in enumerate(periods):      # 逐期間（j 為欄位位置）
                    val = df.iat[i, j]                    # 以位置取得儲存格值（可處理重複科目名）
                    if pd.isna(val):                      # 若值為缺失
                        continue                          # 略過不寫入
                    rows.append((                         # 組裝一筆長格式紀錄
                        str(code), str(stmt_type), freq, str(item),
                        str(period), float(val), i, ts,
                    ))
        if not rows:                                      # 若無任何可寫入的資料
            return 0                                       # 回傳 0
        with self._connect() as conn:                     # 建立連線
            cur = conn.cursor()                           # 取得游標
            cur.executemany(                              # 批次寫入（重複主鍵則覆蓋）
                """
                INSERT OR REPLACE INTO financial_statements
                (code, statement_type, freq, item, period, value, seq, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,                                     # 傳入所有列
            )
            conn.commit()                                 # 提交寫入
        return len(rows)                                  # 回傳寫入筆數

    def load_statements(                                  # 讀出三大報表快取
        self,
        code: str,                                        # 股票代號
        quarterly: bool = False,                          # 是否為季報
    ) -> Dict[str, pd.DataFrame]:
        """
        從快取讀出三大報表並還原為「科目 x 期間」的寬格式 DataFrame。
        會保留原始科目順序、期間由新到舊排列；查無資料的報表回傳空 DataFrame。
        """
        freq = "Q" if quarterly else "Y"                  # 將布林週期轉為代碼
        with self._connect() as conn:                     # 建立連線
            df = pd.read_sql_query(                        # 查詢該股票該週期的所有報表資料
                """
                SELECT statement_type, item, period, value, seq
                FROM financial_statements WHERE code = ? AND freq = ?
                """,
                conn,                                     # 傳入連線
                params=(str(code), freq),                 # 查詢參數
            )
        result: Dict[str, pd.DataFrame] = {}              # 結果字典
        for stmt_type in ["損益表", "資產負債表", "現金流量表"]:  # 依固定順序重建三表
            sub = df[df["statement_type"] == stmt_type]   # 取出該報表的子集
            if sub.empty:                                 # 若無資料
                result[stmt_type] = pd.DataFrame()        # 放入空表
                continue                                  # 處理下一份
            pivot = sub.pivot_table(                      # 以科目為列、期間為欄還原報表
                index="item", columns="period", values="value", aggfunc="last"
            )
            order = (                                     # 依原始序號還原科目順序
                sub.sort_values("seq").drop_duplicates("item")["item"].tolist()
            )
            pivot = pivot.reindex(order)                  # 套用科目順序
            pivot = pivot[sorted(pivot.columns, reverse=True)]  # 期間由新到舊排列
            result[stmt_type] = pivot                     # 放入結果
        return result                                     # 回傳重建後的三大報表

    def has_statements(self, code: str, quarterly: bool = False) -> bool:  # 檢查是否已有快取
        """檢查指定股票與週期的報表是否已存在於快取中。"""    # 方法說明
        freq = "Q" if quarterly else "Y"                  # 將布林週期轉為代碼
        with self._connect() as conn:                     # 建立連線
            cur = conn.cursor()                           # 取得游標
            cur.execute(                                  # 計算符合條件的列數
                "SELECT COUNT(*) FROM financial_statements WHERE code = ? AND freq = ?",
                (str(code), freq),
            )
            return cur.fetchone()[0] > 0                  # 有任何資料即回傳 True


if __name__ == "__main__":                                # 直接執行此檔的簡易示範
    from fetcher import StockFetcher                       # 匯入擷取器以取得合成資料
    db = StockDatabase()                                   # 建立資料庫物件
    fetcher = StockFetcher()                                # 建立擷取器
    n = db.save_price_history("2330", fetcher.generate_sample_price("2330"))  # 寫入合成股價
    print(f"已寫入 {n} 筆股價")                              # 顯示寫入筆數
    db.save_financials(fetcher.generate_sample_financials("2330"))  # 寫入合成財報
    print("讀回財報：", db.load_financials("2330"))          # 讀回並顯示財報
