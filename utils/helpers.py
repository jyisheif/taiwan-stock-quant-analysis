# -*- coding: utf-8 -*-
"""
utils/helpers.py
共用工具函式：放置各模組都會用到的小型輔助函式，
例如數字格式化、股票代號正規化、安全除法、日期處理等。
"""

import re                                              # 匯入正規表達式模組，用於檢查股票代號格式
from datetime import datetime                          # 匯入 datetime，用於取得與格式化日期時間
from typing import Optional, Union                     # 匯入型別註記工具，提升程式可讀性


def normalize_ticker(code: Union[str, int], suffix: str = ".TW") -> str:
    """
    將使用者輸入的股票代號正規化為 Yahoo Finance 可辨識的格式。
    例如輸入 '2330' 會轉成 '2330.TW'。
    """
    text = str(code).strip().upper()                   # 將輸入轉成字串、去除前後空白並轉大寫
    if "." in text:                                    # 若已含有後綴（例如 2330.TW）
        return text                                    # 直接回傳，不重複加後綴
    return f"{text}{suffix}"                            # 否則在純數字代號後接上市場後綴


def is_valid_tw_ticker(code: Union[str, int]) -> bool:
    """
    檢查是否為合法的台股代號（純數字、4 到 6 碼）。
    回傳 True 表示格式正確。
    """
    text = str(code).strip()                            # 將輸入轉為字串並去除空白
    text = text.split(".")[0]                           # 若帶有後綴，只取小數點前的代號部分
    return bool(re.fullmatch(r"\d{4,6}", text))         # 用正規表達式驗證是否為 4~6 位純數字


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    安全除法：避免分母為 0 時程式拋出例外。
    當分母為 0 或無效時，回傳預設值 default。
    """
    try:                                                # 嘗試執行除法
        if denominator == 0:                            # 若分母為 0
            return default                              # 回傳預設值，避免除以零錯誤
        return numerator / denominator                  # 正常情況回傳相除結果
    except (TypeError, ZeroDivisionError):              # 若型別錯誤或除零例外
        return default                                  # 一律回傳預設值


def format_number(value: Optional[float], decimals: int = 2) -> str:
    """
    將數字格式化為帶千分位、固定小數位的字串，便於畫面顯示。
    若值為 None 或無法轉換則回傳 'N/A'。
    """
    if value is None:                                   # 若傳入值為 None
        return "N/A"                                    # 回傳 'N/A' 字串
    try:                                                # 嘗試格式化數字
        return f"{value:,.{decimals}f}"                 # 套用千分位與指定小數位數
    except (TypeError, ValueError):                     # 若值無法被格式化
        return "N/A"                                    # 回傳 'N/A'


def format_percent(value: Optional[float], decimals: int = 2) -> str:
    """
    將小數（例如 0.123）格式化為百分比字串（例如 '12.30%'）。
    """
    if value is None:                                   # 若傳入值為 None
        return "N/A"                                    # 回傳 'N/A'
    try:                                                # 嘗試轉換為百分比
        return f"{value * 100:.{decimals}f}%"           # 乘以 100 並加上百分號
    except (TypeError, ValueError):                     # 若值無法格式化
        return "N/A"                                    # 回傳 'N/A'


def today_str(fmt: str = "%Y-%m-%d") -> str:
    """
    取得今天日期的字串表示，預設格式為 'YYYY-MM-DD'。
    """
    return datetime.now().strftime(fmt)                 # 取得目前時間並依指定格式轉成字串


if __name__ == "__main__":                              # 直接執行此檔時的簡易示範
    print(normalize_ticker("2330"))                     # 預期輸出 2330.TW
    print(is_valid_tw_ticker("2330"))                   # 預期輸出 True
    print(safe_divide(10, 0))                           # 預期輸出 0.0（避免除零）
    print(format_number(1234567.891))                   # 預期輸出 1,234,567.89
    print(format_percent(0.1234))                       # 預期輸出 12.34%
