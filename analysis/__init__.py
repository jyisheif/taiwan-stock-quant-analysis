# -*- coding: utf-8 -*-
"""analysis 套件：提供量化指標計算、選股篩選與估值模型。"""  # 套件說明

from .quant import (                                   # 從量化模組匯入對外公開項目
    QuantAnalyzer,                                     # 價格類量化分析類別
    FinancialMetrics,                                  # 台股財務指標計算類別
    financial_ratio_trends,                            # 簡易財務比率趨勢函式
)
from .screener import (                                # 從選股模組匯入對外公開項目
    StockScreener,                                     # 選股器
    Strategy,                                          # 策略抽象基底（供自訂策略繼承）
    register_strategy,                                 # 策略註冊裝飾器（供擴充新策略）
    STRATEGY_REGISTRY,                                 # 策略註冊表
)
from .valuation import ValuationModel                  # 對外公開估值模型類別

__all__ = [                                            # 定義 import * 時匯出的名稱
    "QuantAnalyzer",
    "FinancialMetrics",
    "financial_ratio_trends",
    "StockScreener",
    "Strategy",
    "register_strategy",
    "STRATEGY_REGISTRY",
    "ValuationModel",
]
