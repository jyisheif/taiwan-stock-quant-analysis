# -*- coding: utf-8 -*-
"""
analysis/valuation.py
估值模型模組：提供常見的個股估值方法，包含
本益比評價法（PE）、股利折現模型（Gordon 成長模型）與簡易合理價區間。
"""

from __future__ import annotations                        # 啟用延遲型別評估

import os                                                 # 匯入 os 處理路徑
import sys                                                # 匯入 sys 調整搜尋路徑
from typing import Dict, Optional                         # 匯入型別註記工具

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

from utils.helpers import safe_divide                     # 匯入安全除法工具


class ValuationModel:                                      # 定義估值模型類別
    """提供多種個股估值計算方法的工具類別。"""             # 類別說明

    @staticmethod                                          # 靜態方法
    def pe_fair_value(eps: float, target_pe: float) -> float:  # 本益比評價法
        """
        本益比評價：合理股價 = 預估 EPS x 目標本益比。
        """
        if eps is None or target_pe is None:               # 若缺少必要參數
            return 0.0                                      # 回傳 0
        return float(eps * target_pe)                       # 回傳合理股價

    @staticmethod                                          # 靜態方法
    def gordon_growth(                                     # 股利折現（Gordon 成長模型）
        dividend: float,                                   # 最近一期每股股利
        required_return: float,                            # 投資人要求報酬率
        growth_rate: float,                                # 股利永續成長率
    ) -> float:
        """
        Gordon 成長模型：合理價 = 下期股利 / (要求報酬率 - 成長率)。
        要求報酬率須大於成長率，否則模型不成立。
        """
        if required_return <= growth_rate:                 # 若要求報酬率不大於成長率
            return 0.0                                      # 模型不成立，回傳 0
        next_div = dividend * (1 + growth_rate)            # 計算下期預估股利
        return float(safe_divide(next_div, required_return - growth_rate))  # 套用模型公式

    @staticmethod                                          # 靜態方法
    def pb_fair_value(book_value_per_share: float, target_pb: float) -> float:  # 股價淨值比評價
        """
        股價淨值比評價：合理股價 = 每股淨值 x 目標 PB。
        """
        if book_value_per_share is None or target_pb is None:  # 若缺少參數
            return 0.0                                      # 回傳 0
        return float(book_value_per_share * target_pb)      # 回傳合理股價

    @classmethod                                           # 類別方法
    def evaluate(                                          # 綜合估值並給出評價
        cls,
        financials: Dict,                                  # 財報指標字典
        target_pe: float = 15.0,                           # 用於估值的目標本益比
        required_return: float = 0.08,                     # 要求報酬率（折現率）
        growth_rate: float = 0.03,                         # 假設股利成長率
    ) -> Dict[str, float]:
        """
        綜合多種模型估算合理價，並與目前股價比較得出折溢價程度。
        """
        eps = financials.get("eps") or 0.0                 # 取得 EPS（缺值以 0 代替）
        price = financials.get("price") or 0.0             # 取得目前股價
        dividend = (financials.get("dividend_yield") or 0.0) * price  # 由殖利率推估每股股利

        pe_value = cls.pe_fair_value(eps, target_pe)       # 以本益比法估算合理價
        ggm_value = cls.gordon_growth(dividend, required_return, growth_rate)  # 以股利折現法估算

        candidates = [v for v in [pe_value, ggm_value] if v > 0]  # 收集有效的估值結果
        fair_value = sum(candidates) / len(candidates) if candidates else 0.0  # 取平均作為綜合合理價

        upside = safe_divide(fair_value - price, price)    # 計算相對目前股價的潛在漲幅（折溢價）

        return {                                           # 回傳估值結果字典
            "pe_fair_value": round(pe_value, 2),           # 本益比法合理價
            "ggm_fair_value": round(ggm_value, 2),         # 股利折現法合理價
            "fair_value": round(fair_value, 2),            # 綜合合理價
            "current_price": round(price, 2),              # 目前股價
            "upside": round(upside, 4),                    # 潛在漲幅（正為低估、負為高估）
        }


if __name__ == "__main__":                                # 直接執行此檔的簡易示範
    sample = {"eps": 30.0, "price": 600.0, "dividend_yield": 0.025}  # 一組範例財報
    result = ValuationModel.evaluate(sample, target_pe=18)  # 進行綜合估值
    print(result)                                          # 印出估值結果
