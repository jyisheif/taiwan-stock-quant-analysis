# -*- coding: utf-8 -*-
"""
tests/test_analysis.py
針對 analysis 套件（quant / screener / valuation）的單元測試。
全程使用合成資料，不需網路即可執行。
"""

import os                                                  # 匯入 os 處理路徑
import sys                                                 # 匯入 sys 調整搜尋路徑

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

import pandas as pd                                        # 匯入 pandas 檢查結果型別
from data.fetcher import StockFetcher                      # 匯入擷取器以產生合成資料
from analysis.quant import (                               # 匯入量化模組待測項目
    QuantAnalyzer,                                         # 價格類量化分析
    FinancialMetrics,                                      # 台股財務指標計算器
    financial_ratio_trends,                                # 簡易比率趨勢函式
)
from analysis.screener import (                            # 匯入選股相關項目
    StockScreener,                                         # 選股器
    Strategy,                                              # 策略基底
    register_strategy,                                     # 策略註冊裝飾器
    STRATEGY_REGISTRY,                                     # 策略註冊表
    PiotroskiFScoreStrategy,                               # F-Score 策略
)
from analysis.valuation import ValuationModel              # 匯入估值模型類別


def test_quant_summary():                                  # 測試量化指標彙總
    df = StockFetcher().generate_sample_price("2330", days=252)  # 產生一年的合成股價
    summary = QuantAnalyzer(df).summary()                  # 計算所有量化指標
    for key in ["annual_return", "annual_volatility",      # 檢查必要指標皆存在
                "sharpe_ratio", "max_drawdown", "rsi"]:
        assert key in summary                              # 每個指標都應在結果中
    assert -1 <= summary["max_drawdown"] <= 0              # 最大回撤應介於 -1 與 0 之間
    assert 0 <= summary["rsi"] <= 100                      # RSI 應介於 0 與 100 之間


def test_valuation_evaluate():                             # 測試綜合估值
    sample = {"eps": 30.0, "price": 600.0, "dividend_yield": 0.025}  # 範例財報
    result = ValuationModel.evaluate(sample, target_pe=18) # 進行估值
    assert result["pe_fair_value"] == 540.0                # 30 x 18 應為 540
    assert "upside" in result                              # 結果應含潛在漲幅欄位


def test_screener():                                       # 測試選股篩選
    pool = [                                               # 自訂兩檔股票：一檔通過、一檔不通過
        {"code": "AAA", "roe": 0.20, "pe": 12, "eps": 5, "debt_ratio": 0.3, "dividend_yield": 0.04},  # 應通過
        {"code": "BBB", "roe": 0.05, "pe": 40, "eps": 0.5, "debt_ratio": 0.9, "dividend_yield": 0.01}, # 應被濾掉
    ]
    result = StockScreener().screen(pool)                  # 執行篩選
    assert isinstance(result, pd.DataFrame)                # 回傳應為 DataFrame
    assert len(result) == 1                                # 應只有一檔通過
    assert result.iloc[0]["code"] == "AAA"                 # 通過的應為 AAA


def test_financial_ratio_trends():                         # 測試財務比率趨勢計算
    # 建立可控的損益表與資產負債表，方便驗證比率數值
    income = pd.DataFrame(                                 # 損益表（科目 x 期間）
        {"2024-12-31": [1000.0, 400.0, 100.0]},
        index=["營業收入", "營業毛利", "稅後淨利"],
    )
    balance = pd.DataFrame(                               # 資產負債表
        {"2024-12-31": [2000.0, 800.0]},
        index=["資產總額", "負債總額"],
    )
    stmts = {"損益表": income, "資產負債表": balance, "現金流量表": pd.DataFrame()}  # 三大報表
    ratios = financial_ratio_trends(stmts)                # 計算比率
    assert abs(ratios.loc["2024-12-31", "毛利率"] - 0.4) < 1e-9   # 毛利率 = 400/1000 = 0.4
    assert abs(ratios.loc["2024-12-31", "淨利率"] - 0.1) < 1e-9   # 淨利率 = 100/1000 = 0.1
    assert abs(ratios.loc["2024-12-31", "負債比"] - 0.4) < 1e-9   # 負債比 = 800/2000 = 0.4


def test_financial_ratio_trends_missing_data():            # 測試資料不全時不應崩潰
    stmts = {"損益表": pd.DataFrame(), "資產負債表": pd.DataFrame(), "現金流量表": pd.DataFrame()}  # 全空
    ratios = financial_ratio_trends(stmts)                # 計算比率
    assert ratios.empty                                    # 資料不全時應回傳空表而非報錯


def _annual_statements():                                  # 建立可控的年報三大報表（測試用）
    periods = ["2022-12-31", "2023-12-31", "2024-12-31"]   # 三個年度期間
    income = pd.DataFrame(                                 # 損益表
        {
            periods[0]: [1000, 400, 200, 100, 1.0],        # 2022 年數值
            periods[1]: [1100, 440, 220, 110, 1.1],        # 2023 年數值
            periods[2]: [1200, 480, 240, 120, 1.2],        # 2024 年數值
        },
        index=["營業收入", "營業毛利", "營業利益", "稅後淨利", "基本每股盈餘"],
    )
    balance = pd.DataFrame(                                # 資產負債表（存量科目維持固定，方便驗算）
        {p: [2400, 1200, 1200, 1200, 600] for p in periods},
        index=["資產總額", "負債總額", "股東權益", "流動資產", "流動負債"],
    )
    cash = pd.DataFrame(                                   # 現金流量表
        {
            periods[0]: [150, -50],                        # 2022：營業現金流、資本支出
            periods[1]: [160, -50],                        # 2023
            periods[2]: [170, -50],                        # 2024
        },
        index=["營業活動現金流", "資本支出"],
    )
    return {"損益表": income, "資產負債表": balance, "現金流量表": cash}  # 回傳三大報表


def test_financial_metrics_annual():                       # 測試年報財務指標
    market = {"price": 24.0, "shares": 100.0, "market_cap": 2400.0}  # 市場資料
    fm = FinancialMetrics(_annual_statements(), freq="annual", market=market)  # 建立計算器
    assert abs(fm.gross_margin().iloc[-1] - 0.4) < 1e-9    # 毛利率 480/1200 = 0.4
    assert abs(fm.net_margin().iloc[-1] - 0.1) < 1e-9      # 淨利率 120/1200 = 0.1
    assert abs(fm.roe().iloc[-1] - 0.1) < 1e-9             # ROE 120/1200 = 0.1
    assert abs(fm.roa().iloc[-1] - 0.05) < 1e-9            # ROA 120/2400 = 0.05
    assert abs(fm.current_ratio().iloc[-1] - 2.0) < 1e-9   # 流動比率 1200/600 = 2.0
    assert abs(fm.debt_ratio().iloc[-1] - 0.5) < 1e-9      # 負債比率 1200/2400 = 0.5
    assert abs(fm.eps().iloc[-1] - 1.2) < 1e-9             # EPS 最新 1.2
    assert abs(fm.per() - 20.0) < 1e-6                     # PER 24/1.2 = 20
    assert abs(fm.pbr() - 2.0) < 1e-6                      # PBR 24/(1200/100=12) = 2
    assert abs(fm.free_cash_flow().iloc[-1] - 120.0) < 1e-6  # FCF 170-50 = 120
    assert abs(fm.fcf_yield() - 0.05) < 1e-9              # FCF Yield 120/2400 = 0.05
    assert fm.peg() > 0                                    # PEG 應為正值
    yoy = fm.growth("營業收入", "yoy").dropna()            # 營收年增率
    assert abs(yoy.iloc[-1] - (1200 / 1100 - 1)) < 1e-9   # 最新年增率 = 1200/1100 - 1


def test_metrics_to_record_and_screener():                # 測試 FinancialMetrics 餵給選股器
    market = {"price": 24.0, "shares": 100.0, "market_cap": 2400.0, "dividend_yield": 0.03}  # 市場資料
    fm = FinancialMetrics(_annual_statements(), freq="annual", market=market)  # 建立計算器
    record = fm.to_record("2330", name="台積電")           # 轉為選股器紀錄
    assert record["code"] == "2330"                        # 代號正確
    assert "gross_margin" in record and "current_ratio" in record  # 含進階指標
    assert abs(record["gross_margin"] - 0.4) < 1e-9        # 毛利率應為 0.4

    # 進階條件：要求毛利率 >= 0.35 與流動比率 >= 1.5，本筆（0.4 / 2.0）應通過
    screener = StockScreener(
        min_roe=0.05, max_pe=50, min_eps=0.5, max_debt_ratio=0.9,
        min_gross_margin=0.35, min_current_ratio=1.5, min_fcf_yield=0.0,
    )
    assert screener.passes(record) is True                 # 應通過進階條件

    # 將毛利率門檻提高到 0.5，本筆（0.4）應被淘汰
    strict = StockScreener(
        min_roe=0.05, max_pe=50, min_eps=0.5, max_debt_ratio=0.9, min_gross_margin=0.5,
    )
    assert strict.passes(record) is False                  # 應被進階條件淘汰


def test_financial_metrics_quarterly_seasonality():       # 測試季報的季節性處理（TTM / YoY 落後 4 期）
    periods = [                                            # 連續 8 季的期間
        "2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31",
        "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
    ]
    rev = [100, 100, 100, 100, 110, 110, 110, 110]         # 前四季 100、後四季 110（年增 10%）
    eps_q = [0.25] * 8                                     # 每季 EPS 0.25
    income = pd.DataFrame(                                 # 季度損益表
        {p: [rev[i], eps_q[i]] for i, p in enumerate(periods)},
        index=["營業收入", "基本每股盈餘"],
    )
    stmts = {"損益表": income, "資產負債表": pd.DataFrame(), "現金流量表": pd.DataFrame()}  # 報表
    fm = FinancialMetrics(stmts, freq="quarterly")         # 以季報模式建立計算器
    assert abs(fm.eps().dropna().iloc[-1] - 1.0) < 1e-9    # TTM EPS = 0.25 x 4 = 1.0
    yoy = fm.growth("營業收入", "yoy").dropna()            # 營收年增率（落後 4 期比較去年同季）
    assert abs(yoy.iloc[-1] - 0.1) < 1e-9                 # 最新季 110 vs 去年同季 100 = +10%


def _strategy_pool():                                      # 建立策略測試用的股票池
    return [
        {"code": "VAL", "roe": 0.12, "roa": 0.08, "pe": 8, "pb": 1.0, "eps": 3,  # 價值股（便宜）
         "net_margin": 0.1, "gross_margin": 0.3, "current_ratio": 2.0, "debt_ratio": 0.4,
         "fcf_yield": 0.05, "revenue_yoy": 0.02, "dividend_yield": 0.06},
        {"code": "GRW", "roe": 0.25, "roa": 0.15, "pe": 35, "pb": 6.0, "eps": 5,  # 成長股（貴但成長快）
         "net_margin": 0.25, "gross_margin": 0.6, "current_ratio": 1.5, "debt_ratio": 0.5,
         "fcf_yield": 0.01, "revenue_yoy": 0.40, "dividend_yield": 0.005},
        {"code": "QLT", "roe": 0.30, "roa": 0.20, "pe": 18, "pb": 4.0, "eps": 8,  # 品質股（高 ROE/毛利）
         "net_margin": 0.30, "gross_margin": 0.7, "current_ratio": 3.0, "debt_ratio": 0.2,
         "fcf_yield": 0.06, "revenue_yoy": 0.10, "dividend_yield": 0.03},
    ]


def test_strategy_registry():                              # 測試策略註冊表
    strats = StockScreener.available_strategies()           # 取得可用策略
    for name in ["value", "growth", "quality", "magic_formula", "piotroski"]:  # 五個內建策略
        assert name in strats                              # 應皆已註冊


def test_value_growth_quality_strategies():                # 測試三種風格策略的排序傾向
    pool = _strategy_pool()                                # 股票池
    value_top = StockScreener().screen(pool, strategy="value", apply_filter=False).iloc[0]["code"]  # 價值型第一
    growth_top = StockScreener().screen(pool, strategy="growth", apply_filter=False).iloc[0]["code"]  # 成長型第一
    quality_top = StockScreener().screen(pool, strategy="quality", apply_filter=False).iloc[0]["code"]  # 品質型第一
    assert value_top == "VAL"                              # 價值型應選出便宜的 VAL
    assert growth_top == "GRW"                             # 成長型應選出高成長的 GRW
    assert quality_top == "QLT"                            # 品質型應選出高品質的 QLT


def test_magic_formula_strategy():                         # 測試魔法公式排名
    pool = _strategy_pool()                                # 股票池
    res = StockScreener().screen(pool, strategy="magic_formula", apply_filter=False)  # 執行魔法公式
    assert "earnings_yield" in res.columns and "roc" in res.columns  # 應含盈餘殖利率與資本報酬率
    assert "mf_combined" in res.columns                    # 應含合併名次
    assert len(res) == len(pool)                           # 全部股票皆參與排名
    assert res.iloc[0]["score"] >= res.iloc[-1]["score"]   # 已依分數由高到低排序


def test_piotroski_fscore():                               # 測試 Piotroski F-Score
    rec = {                                                # 一筆當期優於上期、體質良好的紀錄
        "roa": 0.10, "operating_cf": 120, "net_income": 100,  # ROA>0、CFO>0、CFO>淨利
        "gross_margin": 0.40, "current_ratio": 2.2, "debt_ratio": 0.3, "asset_turnover": 0.9,
        "shares": 100,                                     # 流通股數
        "prev": {                                          # 上期（各項皆較差，代表本期改善）
            "roa": 0.08, "gross_margin": 0.38, "current_ratio": 2.0,
            "debt_ratio": 0.35, "asset_turnover": 0.85, "shares": 100,
        },
    }
    score, detail = PiotroskiFScoreStrategy.fscore(rec)    # 計算 F-Score
    assert score == 9                                      # 9 項全數達標
    assert detail["ROA為正"] == 1 and detail["毛利率上升"] == 1  # 抽查兩項明細


def test_fscore_from_metrics():                            # 測試由 FinancialMetrics 算 F-Score
    fm = FinancialMetrics(_annual_statements(), freq="annual",  # 以年報資料建立計算器
                          market={"price": 24.0, "shares": 100.0, "market_cap": 2400.0})
    score, detail = StockScreener.fscore_from_metrics(fm)  # 由時間序列計算 F-Score
    assert 0 <= score <= 9                                 # 分數須落在 0~9
    assert isinstance(detail, dict) and len(detail) == 9   # 應有 9 項訊號明細


def test_register_custom_strategy():                       # 測試自訂新策略可被註冊與使用
    @register_strategy("__test_dividend__")                # 以裝飾器註冊一個臨時策略
    class _DividendStrategy(Strategy):                     # 自訂：純殖利率排序
        description = "測試用殖利率策略"                     # 說明
        def score_one(self, rec):                          # 打分：殖利率越高越好
            return float(rec.get("dividend_yield") or 0)
    try:                                                   # 使用後清理註冊表
        res = StockScreener().screen(_strategy_pool(), strategy="__test_dividend__", apply_filter=False)
        assert res.iloc[0]["code"] == "VAL"                # VAL 殖利率最高，應排第一
    finally:                                               # 確保移除臨時策略避免污染
        STRATEGY_REGISTRY.pop("__test_dividend__", None)   # 從註冊表移除


if __name__ == "__main__":                                 # 直接執行時逐一呼叫測試
    test_quant_summary()                                   # 執行量化指標測試
    test_valuation_evaluate()                              # 執行估值測試
    test_screener()                                        # 執行選股測試
    test_financial_ratio_trends()                          # 執行財務比率趨勢測試
    test_financial_ratio_trends_missing_data()             # 執行比率趨勢容錯測試
    test_financial_metrics_annual()                        # 執行年報財務指標測試
    test_metrics_to_record_and_screener()                  # 執行指標餵選股器測試
    test_financial_metrics_quarterly_seasonality()         # 執行季報季節性測試
    test_strategy_registry()                               # 執行策略註冊表測試
    test_value_growth_quality_strategies()                 # 執行風格策略測試
    test_magic_formula_strategy()                          # 執行魔法公式測試
    test_piotroski_fscore()                                # 執行 F-Score 測試
    test_fscore_from_metrics()                             # 執行由指標算 F-Score 測試
    test_register_custom_strategy()                        # 執行自訂策略註冊測試
    print("[PASS] analysis 套件所有測試通過！")              # 全數通過則印出成功訊息
