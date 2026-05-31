# -*- coding: utf-8 -*-
"""
tests/test_helpers.py
針對 utils/helpers.py 的單元測試，驗證每個工具函式的行為是否正確。
可用 `pytest` 執行，也可直接 `python tests/test_helpers.py` 執行。
"""

import os                                                  # 匯入 os 模組以處理路徑
import sys                                                 # 匯入 sys 模組以調整模組搜尋路徑

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑，確保能 import

from utils.helpers import (                                # 從待測模組匯入要測試的函式
    normalize_ticker,                                      # 股票代號正規化函式
    is_valid_tw_ticker,                                    # 台股代號驗證函式
    safe_divide,                                           # 安全除法函式
    format_number,                                         # 數字格式化函式
    format_percent,                                        # 百分比格式化函式
)


def test_normalize_ticker():                               # 測試代號正規化
    assert normalize_ticker("2330") == "2330.TW"           # 純數字應補上 .TW 後綴
    assert normalize_ticker("2330.TW") == "2330.TW"        # 已有後綴則維持不變
    assert normalize_ticker(2317) == "2317.TW"             # 整數輸入也應正確處理


def test_is_valid_tw_ticker():                             # 測試代號驗證
    assert is_valid_tw_ticker("2330") is True              # 4 碼數字為合法
    assert is_valid_tw_ticker("23") is False               # 少於 4 碼為非法
    assert is_valid_tw_ticker("abcd") is False             # 含字母為非法


def test_safe_divide():                                    # 測試安全除法
    assert safe_divide(10, 2) == 5.0                       # 正常除法應正確
    assert safe_divide(10, 0) == 0.0                       # 除以零應回傳預設值 0
    assert safe_divide(10, 0, default=-1) == -1            # 可自訂除零時的回傳值


def test_format_number():                                  # 測試數字格式化
    assert format_number(1234.5) == "1,234.50"             # 應有千分位與兩位小數
    assert format_number(None) == "N/A"                    # None 應回傳 N/A


def test_format_percent():                                 # 測試百分比格式化
    assert format_percent(0.1234) == "12.34%"              # 小數應轉為百分比
    assert format_percent(None) == "N/A"                   # None 應回傳 N/A


if __name__ == "__main__":                                 # 直接執行時逐一呼叫測試
    test_normalize_ticker()                                # 執行代號正規化測試
    test_is_valid_tw_ticker()                              # 執行代號驗證測試
    test_safe_divide()                                     # 執行安全除法測試
    test_format_number()                                   # 執行數字格式化測試
    test_format_percent()                                  # 執行百分比格式化測試
    print("[PASS] utils/helpers.py 所有測試通過！")          # 全數通過則印出成功訊息
