# -*- coding: utf-8 -*-
"""
tests/test_data.py
針對 data 套件（fetcher / processor / database）的單元測試。
測試全程使用合成資料，不需網路即可執行。
"""

import os                                                  # 匯入 os 處理路徑
import sys                                                 # 匯入 sys 調整搜尋路徑
import tempfile                                            # 匯入 tempfile 以建立暫時資料庫檔

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

import pandas as pd                                        # 匯入 pandas 以檢查資料型別
from data.fetcher import StockFetcher, INCOME_STMT_MAP     # 匯入資料擷取類別與損益表對照表
from data.processor import DataProcessor                   # 匯入資料處理類別
from data.database import StockDatabase                    # 匯入資料庫類別


def test_fetcher_sample_price():                           # 測試合成股價產生器
    df = StockFetcher().generate_sample_price("2330", days=100)  # 產生 100 天合成股價
    assert isinstance(df, pd.DataFrame)                    # 回傳值應為 DataFrame
    assert len(df) == 100                                  # 筆數應等於指定天數
    for col in ["open", "high", "low", "close", "volume"]: # 檢查必要欄位
        assert col in df.columns                           # 每個欄位都應存在


def test_fetcher_sample_financials():                      # 測試合成財報產生器
    fin = StockFetcher().generate_sample_financials("2330")  # 產生合成財報
    assert fin["code"] == "2330"                           # 代號應正確
    assert 0 < fin["roe"] < 1                              # ROE 應介於 0~1 之間（比例形式）
    assert fin["pe"] > 0                                   # 本益比應為正數


def test_processor_enrich():                               # 測試資料加工流程
    raw = StockFetcher().generate_sample_price("2317", days=120)  # 產生合成股價
    enriched = DataProcessor.enrich(raw)                   # 套用完整加工
    assert "daily_return" in enriched.columns              # 應含日報酬率欄位
    assert "ma20" in enriched.columns                      # 應含 20 日均線欄位
    assert "volatility_20" in enriched.columns             # 應含 20 日波動率欄位


def test_database_roundtrip():                             # 測試資料庫寫入與讀取
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # 建立暫時資料庫檔
    tmp.close()                                            # 關閉檔案以便 SQLite 使用
    db = StockDatabase(db_path=tmp.name)                   # 以暫時檔建立資料庫物件
    fetcher = StockFetcher()                                # 建立擷取器
    n = db.save_price_history("2454", fetcher.generate_sample_price("2454", days=50))  # 寫入股價
    assert n == 50                                         # 寫入筆數應為 50
    loaded = db.load_price_history("2454")                 # 讀回股價
    assert len(loaded) == 50                               # 讀回筆數應一致
    db.save_financials(fetcher.generate_sample_financials("2454"))  # 寫入財報
    fin = db.load_financials("2454")                       # 讀回財報
    assert fin is not None and fin["code"] == "2454"       # 應成功讀回且代號正確
    try:                                                   # 嘗試清理暫時檔
        os.unlink(tmp.name)                                # 刪除暫時資料庫檔
    except PermissionError:                                # Windows 上檔案有時暫被鎖定
        pass                                               # 清理失敗不影響測試結果


def test_fetcher_sample_info():                            # 測試合成基本資料產生器
    info = StockFetcher().generate_sample_info("2330")     # 產生合成基本資料
    assert info["原始代號"] == "2330"                       # 代號應正確
    assert "簡稱" in info and "市值" in info                # 應含必要的中文欄位


def test_fetcher_sample_statements():                      # 測試合成三大報表
    fetcher = StockFetcher()                                # 建立擷取器
    income = fetcher.generate_sample_statement("2330", "income", quarterly=False)   # 年度損益表
    balance = fetcher.generate_sample_statement("2330", "balance", quarterly=True)  # 季度資產負債表
    cash = fetcher.generate_sample_statement("2330", "cashflow", quarterly=False)   # 年度現金流量表
    assert "營業收入" in income.index                       # 損益表應含中文科目「營業收入」
    assert "資產總額" in balance.index                      # 資產負債表應含「資產總額」
    assert "營業活動現金流" in cash.index                   # 現金流量表應含「營業活動現金流」
    # 驗證會計關係：毛利 = 收入 - 成本（取第一期檢查）
    col = income.columns[0]                                # 取第一個期間欄位
    assert income.loc["營業毛利", col] == (                # 毛利應等於
        income.loc["營業收入", col] - income.loc["營業成本", col]  # 收入扣除成本
    )


def test_translate_index():                                # 測試科目翻譯函式
    raw = pd.DataFrame(                                    # 建立一份英文科目的假財報
        {"2024-12-31": [100, 60]},
        index=["Total Revenue", "Cost Of Revenue"],
    )
    translated = StockFetcher._translate_index(raw, INCOME_STMT_MAP)  # 進行翻譯
    assert "營業收入" in translated.index                   # Total Revenue 應翻為「營業收入」
    assert "營業成本" in translated.index                   # Cost Of Revenue 應翻為「營業成本」


def test_period_to_months():                               # 測試區間字串換算月數（twstock 用）
    assert StockFetcher._period_to_months("6mo") == 6      # 6 個月應為 6
    assert StockFetcher._period_to_months("1y") == 12      # 1 年應為 12 個月
    assert StockFetcher._period_to_months("2y") == 24      # 2 年應為 24 個月
    assert StockFetcher._period_to_months("bad") == 12     # 無法解析時回傳預設 12


def test_get_financial_statements_structure():             # 測試一次取得三大報表的結構
    stmts = StockFetcher().get_financial_statements("2330", quarterly=False)  # 取得三大報表
    assert set(stmts.keys()) == {"損益表", "資產負債表", "現金流量表"}  # 鍵名應為三大報表
    for df in stmts.values():                              # 每份報表
        assert isinstance(df, pd.DataFrame) and not df.empty  # 都應為非空 DataFrame


def test_database_statements_roundtrip():                  # 測試三大報表快取寫入與讀取
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # 建立暫時資料庫檔
    tmp.close()                                            # 關閉以便 SQLite 使用
    db = StockDatabase(db_path=tmp.name)                   # 以暫時檔建立資料庫物件
    fetcher = StockFetcher()                                # 建立擷取器
    stmts = {                                              # 用合成資料組成三大報表
        "損益表": fetcher.generate_sample_statement("2330", "income", quarterly=False),
        "資產負債表": fetcher.generate_sample_statement("2330", "balance", quarterly=False),
        "現金流量表": fetcher.generate_sample_statement("2330", "cashflow", quarterly=False),
    }
    assert db.has_statements("2330", quarterly=False) is False  # 寫入前應無快取
    n = db.save_statements("2330", stmts, quarterly=False)  # 寫入快取
    assert n > 0                                           # 應有寫入筆數
    assert db.has_statements("2330", quarterly=False) is True   # 寫入後應有快取
    loaded = db.load_statements("2330", quarterly=False)   # 讀回快取
    assert "營業收入" in loaded["損益表"].index             # 應還原損益表科目
    assert "資產總額" in loaded["資產負債表"].index          # 應還原資產負債表科目
    # 驗證數值一致（比較第一個科目第一期）
    orig = stmts["損益表"].iloc[0, 0]                       # 原始值
    col0 = sorted(loaded["損益表"].columns, reverse=True)[0]  # 還原後最新一期
    assert abs(loaded["損益表"].loc["營業收入", col0] - orig) < 1.0  # 數值應一致
    try:                                                   # 嘗試清理暫時檔
        os.unlink(tmp.name)                                # 刪除暫時資料庫檔
    except PermissionError:                                # Windows 上檔案有時暫被鎖定
        pass                                               # 清理失敗不影響測試結果


if __name__ == "__main__":                                 # 直接執行時逐一呼叫測試
    test_fetcher_sample_price()                            # 執行股價產生器測試
    test_fetcher_sample_financials()                       # 執行財報產生器測試
    test_fetcher_sample_info()                             # 執行基本資料產生器測試
    test_fetcher_sample_statements()                       # 執行三大報表產生器測試
    test_translate_index()                                 # 執行科目翻譯測試
    test_period_to_months()                                # 執行區間換算測試
    test_processor_enrich()                                # 執行資料加工測試
    test_database_roundtrip()                              # 執行資料庫讀寫測試
    test_database_statements_roundtrip()                   # 執行報表快取讀寫測試
    print("[PASS] data 套件所有測試通過！")                  # 全數通過則印出成功訊息
