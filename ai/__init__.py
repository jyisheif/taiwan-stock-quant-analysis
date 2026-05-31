# -*- coding: utf-8 -*-
"""ai 套件：整合大型語言模型（LLM）產生投資分析建議。"""  # 套件說明

from .analyst import (                                  # 從分析模組匯入對外公開項目
    AIAnalyst,                                          # AI 分析師類別
    AnalysisResult,                                     # 結構化分析結果模型
    get_ai_analysis,                                    # 取得 AI 結構化分析的核心函式
    SYSTEM_PROMPT,                                      # 專業台股分析師系統提示詞
)

__all__ = ["AIAnalyst", "AnalysisResult", "get_ai_analysis", "SYSTEM_PROMPT"]  # import * 匯出名稱
