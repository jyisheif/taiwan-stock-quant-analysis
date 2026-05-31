# -*- coding: utf-8 -*-
"""
tests/test_ai.py
針對 ai/analyst.py 的單元測試。
測試以「無 API 金鑰」情境執行，驗證本地規則式分析能正確產出。
"""

import os                                                  # 匯入 os 處理路徑
import sys                                                 # 匯入 sys 調整搜尋路徑

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

from ai.analyst import (                                   # 匯入 AI 分析模組待測項目
    AIAnalyst,                                             # AI 分析師類別
    AnalysisResult,                                        # 結構化分析結果模型
    get_ai_analysis,                                       # 結構化分析核心函式
    build_analysis_prompt,                                 # 提示詞組裝函式
)


def _sample_inputs():                                      # 建立測試用的範例輸入
    fin = {"code": "2330", "name": "台積電", "price": 600,  # 範例財報
           "pe": 18, "eps": 33, "roe": 0.25}
    quant = {"annual_return": 0.18, "annual_volatility": 0.22,  # 範例量化指標
             "sharpe_ratio": 1.2, "max_drawdown": -0.15}
    val = {"fair_value": 680, "upside": 0.13}              # 範例估值結果
    return fin, quant, val                                 # 回傳三組輸入


def test_build_prompt():                                   # 測試提示詞組裝
    fin, quant, val = _sample_inputs()                     # 取得範例輸入
    prompt = AIAnalyst(api_key="").build_prompt(fin, quant, val)  # 組裝提示詞
    assert "台積電" in prompt                              # 提示詞應包含股票名稱
    assert "操作建議" in prompt                            # 提示詞應要求操作建議


def test_rule_based_analysis():                            # 測試本地規則式分析
    fin, quant, val = _sample_inputs()                     # 取得範例輸入
    analyst = AIAnalyst(api_key="")                        # 不給金鑰，強制走本地分析
    report = analyst.analyze(fin, quant, val)              # 產生分析文字
    assert isinstance(report, str)                         # 結果應為字串
    assert len(report) > 0                                 # 結果不應為空
    assert "操作建議" in report                            # 分析中應包含操作建議
    assert "買進" in report                                # 此範例為低估且高 ROE，應建議買進


def _buy_data():                                           # 強烈偏多的測試資料
    return {
        "financials": {"name": "台積電", "price": 600, "pe": 18, "eps": 33,  # 財報
                       "roe": 0.25, "net_margin": 0.40, "debt_ratio": 0.28, "current_ratio": 2.5},
        "valuation": {"fair_value": 720, "upside": 0.20},   # 估值（低估 20%）
        "growth": {"revenue_yoy": 0.25},                    # 成長（高成長）
        "technical": {"annual_return": 0.18, "sharpe_ratio": 1.3, "rsi": 55, "max_drawdown": -0.15},  # 技術
        "risk": {"debt_ratio": 0.28, "volatility": 0.22},   # 風險（低）
    }


def _sell_data():                                          # 偏空的測試資料
    return {
        "financials": {"roe": 0.03, "net_margin": 0.02, "debt_ratio": 0.8, "current_ratio": 0.8},  # 財報差
        "valuation": {"fair_value": 50, "upside": -0.25},   # 估值（高估 25%）
        "growth": {"revenue_yoy": -0.10},                   # 成長（衰退）
        "technical": {"annual_return": -0.05, "sharpe_ratio": -0.2, "rsi": 80, "max_drawdown": -0.45},  # 技術差
        "risk": {"debt_ratio": 0.8, "volatility": 0.6},     # 風險（高）
    }


def test_analysis_result_model_clamp():                    # 測試結構化模型與範圍夾限
    r = AnalysisResult(                                    # 故意給超界的分數與信心
        recommendation="買入", score=99, confidence=200.0,
        target_price=None, upside_potential=None, risk_level="中",
        key_reasons=["測試"], summary="測試",
    )
    assert r.score == 10                                   # 分數應被夾限到 10
    assert r.confidence == 100.0                           # 信心應被夾限到 100


def test_build_analysis_prompt_sections():                 # 測試提示詞包含各面向
    prompt = build_analysis_prompt("2330", _buy_data())    # 組裝提示詞
    for section in ["財報基本面", "估值", "成長性", "技術面", "風險"]:  # 五大面向
        assert section in prompt                           # 皆應出現在提示詞中
    assert "2330" in prompt                                # 應包含股票代號


def test_get_ai_analysis_buy_offline():                    # 測試離線（規則式）偏多情境
    result = get_ai_analysis("2330", _buy_data(), api_key="")  # 強制離線
    assert isinstance(result, AnalysisResult)              # 應回傳結構化結果
    assert result.score > 0                                # 偏多情境分數應為正
    assert result.recommendation in ("強力買入", "買入")    # 應建議買進
    assert result.target_price == 720.0                    # 目標價取自合理價
    assert result.upside_potential == 20.0                 # 潛在漲幅為 20%
    assert 0 <= result.confidence <= 100                   # 信心在合理範圍
    assert len(result.key_reasons) >= 1                    # 至少一條理由


def test_get_ai_analysis_sell_offline():                   # 測試離線（規則式）偏空情境
    result = get_ai_analysis("9999", _sell_data(), api_key="")  # 強制離線
    assert result.score < 0                                # 偏空情境分數應為負
    assert result.recommendation in ("賣出", "強力賣出")    # 應建議賣出
    assert result.risk_level == "高"                        # 高負債高波動應為高風險


if __name__ == "__main__":                                 # 直接執行時逐一呼叫測試
    test_build_prompt()                                    # 執行提示詞組裝測試
    test_rule_based_analysis()                             # 執行規則式分析測試
    test_analysis_result_model_clamp()                     # 執行模型夾限測試
    test_build_analysis_prompt_sections()                  # 執行提示詞面向測試
    test_get_ai_analysis_buy_offline()                     # 執行偏多情境測試
    test_get_ai_analysis_sell_offline()                    # 執行偏空情境測試
    print("[PASS] ai 套件所有測試通過！")                    # 全數通過則印出成功訊息
