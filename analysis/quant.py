# -*- coding: utf-8 -*-
"""
analysis/quant.py
量化分析模組：根據歷史股價計算常見的量化績效與風險指標，
包含年化報酬率、年化波動率、夏普比率、最大回撤與技術指標（RSI）。
"""

from __future__ import annotations                        # 啟用延遲型別評估

import os                                                 # 匯入 os 處理路徑
import sys                                                # 匯入 sys 調整搜尋路徑
from typing import Dict                                   # 匯入型別註記工具

import numpy as np                                        # 匯入 numpy 做數值運算
import pandas as pd                                       # 匯入 pandas 處理表格資料

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

from config import settings                               # 匯入全域設定（無風險利率、交易日數）
from utils.helpers import safe_divide                     # 匯入安全除法工具


class QuantAnalyzer:                                       # 定義量化分析類別
    """以歷史股價序列計算量化指標的工具類別。"""           # 類別說明

    def __init__(self, df: pd.DataFrame):                 # 建構子，輸入含 close 欄位的股價資料
        self.df = df.copy()                               # 複製資料避免修改原始 DataFrame
        if "daily_return" not in self.df.columns:         # 若尚未計算日報酬率
            self.df["daily_return"] = self.df["close"].pct_change()  # 補上日報酬率欄位
        self.returns = self.df["daily_return"].dropna()   # 取出有效的日報酬率序列（去除首列 NaN）

    def annual_return(self) -> float:                     # 計算年化報酬率
        """以平均日報酬率推算年化報酬率。"""               # 方法說明
        if self.returns.empty:                            # 若無報酬率資料
            return 0.0                                     # 回傳 0
        mean_daily = self.returns.mean()                  # 計算平均日報酬率
        return float((1 + mean_daily) ** settings.trading_days - 1)  # 複利推算為年化報酬率

    def annual_volatility(self) -> float:                 # 計算年化波動率
        """以日報酬率標準差推算年化波動率。"""             # 方法說明
        if self.returns.empty:                            # 若無資料
            return 0.0                                     # 回傳 0
        return float(self.returns.std() * np.sqrt(settings.trading_days))  # 日標準差乘以根號交易日數

    def sharpe_ratio(self) -> float:                      # 計算夏普比率
        """（年化報酬率 - 無風險利率）/ 年化波動率。"""      # 方法說明
        excess = self.annual_return() - settings.risk_free_rate  # 計算超額報酬
        return float(safe_divide(excess, self.annual_volatility()))  # 以安全除法避免除以零

    def max_drawdown(self) -> float:                      # 計算最大回撤
        """計算期間內從高點下跌的最大幅度（負值）。"""       # 方法說明
        if self.df.empty:                                 # 若無資料
            return 0.0                                     # 回傳 0
        cum = (1 + self.returns).cumprod()                # 計算累積淨值曲線
        running_max = cum.cummax()                        # 計算歷史累積最高點
        drawdown = (cum - running_max) / running_max      # 計算每個時點的回撤幅度
        return float(drawdown.min()) if not drawdown.empty else 0.0  # 取最小值（最大回撤）

    def rsi(self, period: int = 14) -> float:             # 計算相對強弱指標（RSI）
        """計算最新的 RSI 值，衡量股價超買或超賣。"""        # 方法說明
        delta = self.df["close"].diff()                   # 計算每日價格變動
        gain = delta.clip(lower=0)                        # 取出上漲部分（負值歸零）
        loss = -delta.clip(upper=0)                       # 取出下跌部分並轉正
        avg_gain = gain.rolling(period).mean()            # 計算平均漲幅
        avg_loss = loss.rolling(period).mean()            # 計算平均跌幅
        rs = safe_divide(avg_gain.iloc[-1], avg_loss.iloc[-1], default=0.0)  # 計算相對強度 RS
        if avg_loss.iloc[-1] == 0:                        # 若平均跌幅為 0（連續上漲）
            return 100.0                                   # RSI 為極值 100
        return float(100 - (100 / (1 + rs)))              # 套用 RSI 公式回傳數值

    def summary(self) -> Dict[str, float]:                # 彙總所有指標
        """一次回傳所有量化指標的字典，方便顯示。"""         # 方法說明
        return {                                          # 組裝指標字典
            "annual_return": self.annual_return(),        # 年化報酬率
            "annual_volatility": self.annual_volatility(),  # 年化波動率
            "sharpe_ratio": self.sharpe_ratio(),          # 夏普比率
            "max_drawdown": self.max_drawdown(),          # 最大回撤
            "rsi": self.rsi(),                            # 最新 RSI
        }


def financial_ratio_trends(statements: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    從三大報表計算逐期財務比率趨勢：毛利率、淨利率、負債比。
    輸入為 {'損益表': df, '資產負債表': df, '現金流量表': df}（科目為中文列名）。
    回傳以「期間」為索引（由舊到新）、比率（小數形式）為欄位的 DataFrame；
    缺少對應科目時該比率欄位會自動略過，確保不因資料不全而中斷。
    """
    income = statements.get("損益表")                       # 取出損益表
    balance = statements.get("資產負債表")                  # 取出資產負債表

    def row(df: pd.DataFrame, item: str):                  # 取得某科目該列（找不到回傳 None）
        """安全地從報表取出指定科目的數值序列。"""           # 內部工具說明
        if df is not None and not df.empty and item in df.index:  # 若報表存在且含此科目
            return df.loc[item]                            # 回傳該科目所有期間的值
        return None                                        # 否則回傳 None

    revenue = row(income, "營業收入")                       # 營業收入序列
    gross = row(income, "營業毛利")                         # 營業毛利序列
    net = row(income, "稅後淨利")                           # 稅後淨利序列
    assets = row(balance, "資產總額")                       # 資產總額序列
    liab = row(balance, "負債總額")                         # 負債總額序列

    result = pd.DataFrame()                                # 建立空結果表
    if revenue is not None and gross is not None:          # 若有收入與毛利
        result["毛利率"] = gross / revenue                  # 毛利率 = 毛利 / 收入（依期間自動對齊）
    if revenue is not None and net is not None:            # 若有收入與淨利
        result["淨利率"] = net / revenue                    # 淨利率 = 淨利 / 收入
    if assets is not None and liab is not None:            # 若有資產與負債
        result["負債比"] = liab / assets                    # 負債比 = 負債 / 資產

    if not result.empty:                                   # 若有計算出任何比率
        result = result.sort_index()                       # 依期間（日期字串）由舊到新排序
    return result                                          # 回傳比率趨勢表


class FinancialMetrics:
    """
    台股常用財務指標計算器（以 pandas 向量化計算）。

    輸入為 fetcher 產出的三大報表字典（科目為中文列名、欄為各期間），
    並可選擇性傳入市場資料（股價、流通股數、市值）以計算評價類指標。

    === 財報季節性處理 ===
    台股季報具有明顯季節性（單季數字會因淡旺季波動），本類別以兩種方式處理：
      1. YoY 比較採「年度落後期數」：季報比較去年同季（落後 4 期）、年報比較去年（落後 1 期）。
      2. 對「流量科目」（營收、淨利、現金流）提供 TTM（近四季滾動加總），
         以消除單季季節性，使 ROE、EPS、FCF 等指標更具可比性。
    所有計算皆回傳以「期間」為索引（由舊到新）的 pandas Series，屬向量化運算。
    """

    # 流量科目（橫跨一段期間累積，季報需 TTM 處理）與存量科目（時點餘額）區分
    FLOW_ITEMS = {"營業收入", "營業毛利", "營業利益", "稅後淨利",  # 損益表流量科目
                  "營業活動現金流", "投資活動現金流", "籌資活動現金流",  # 現金流量表流量科目
                  "自由現金流", "資本支出"}                       # 其他流量科目

    def __init__(                                          # 建構子
        self,
        statements: Dict[str, pd.DataFrame],              # 三大報表字典
        freq: str = "annual",                             # 報表週期（'annual' 年報 / 'quarterly' 季報）
        market: Optional[Dict[str, Any]] = None,          # 市場資料（price/shares/market_cap）
    ):
        self.income = statements.get("損益表")             # 損益表
        self.balance = statements.get("資產負債表")        # 資產負債表
        self.cashflow = statements.get("現金流量表")       # 現金流量表
        self.freq = freq                                  # 報表週期
        self.market = market or {}                        # 市場資料（缺省為空字典）
        self.lag = 4 if freq == "quarterly" else 1        # YoY 落後期數：季報 4、年報 1

    # ------------------------------------------------------------------
    # 基礎工具：取出科目序列、TTM 與成長率（皆為向量化運算）
    # ------------------------------------------------------------------

    def _series(self, df: Optional[pd.DataFrame], item: str) -> pd.Series:
        """從報表取出指定科目並轉為數值 Series（依期間由舊到新排序）。"""  # 方法說明
        if df is None or df.empty or item not in df.index:  # 若報表或科目不存在
            return pd.Series(dtype="float64")             # 回傳空 Series
        s = df.loc[item]                                  # 取出該科目所有期間的值
        if isinstance(s, pd.DataFrame):                   # 若科目名重複（取第一列）
            s = s.iloc[0]                                 # 只取第一筆
        s = pd.to_numeric(s, errors="coerce")             # 轉為數值，無法轉換者設為 NaN
        return s.sort_index()                             # 依期間（日期字串）由舊到新排序

    def _ttm(self, s: pd.Series, item: str) -> pd.Series:
        """
        對流量科目做季節性平滑：季報回傳近四季滾動加總（TTM），年報維持原值。
        存量科目（如資產、權益）不適用 TTM，原樣回傳。
        """
        if s.empty:                                       # 若序列為空
            return s                                      # 原樣回傳
        if self.freq == "quarterly" and item in self.FLOW_ITEMS:  # 季報且為流量科目
            return s.rolling(4, min_periods=4).sum()      # 近四季滾動加總（消除季節性）
        return s                                          # 其餘情況維持原值

    def growth(self, item: str, kind: str = "yoy") -> pd.Series:
        """
        計算成長率（向量化）。kind='yoy' 年增率、'qoq' 季增率（僅季報有意義）。
        年增率自動依週期採用正確落後期數以對齊去年同期，處理季節性。
        """
        s = self._series(self.income, item)               # 預設先從損益表找科目
        if s.empty:                                       # 若損益表沒有
            s = self._series(self.cashflow, item)         # 再嘗試現金流量表
        if s.empty:                                       # 若仍找不到
            return pd.Series(dtype="float64")             # 回傳空 Series
        periods = 1 if kind == "qoq" else self.lag        # QoQ 落後 1 期；YoY 依週期落後
        return s.pct_change(periods=periods)              # 以 pandas 向量化計算期間變化率

    # ------------------------------------------------------------------
    # 1. 獲利能力指標（毛利率 / 營業利益率 / 淨利率 / ROE / ROA）
    # ------------------------------------------------------------------

    def gross_margin(self) -> pd.Series:                  # 毛利率
        """毛利率 = 營業毛利 / 營業收入。"""               # 方法說明
        return self._series(self.income, "營業毛利") / self._series(self.income, "營業收入")  # 向量化相除

    def operating_margin(self) -> pd.Series:              # 營業利益率
        """營業利益率 = 營業利益 / 營業收入。"""           # 方法說明
        return self._series(self.income, "營業利益") / self._series(self.income, "營業收入")  # 向量化相除

    def net_margin(self) -> pd.Series:                    # 淨利率
        """淨利率 = 稅後淨利 / 營業收入。"""               # 方法說明
        return self._series(self.income, "稅後淨利") / self._series(self.income, "營業收入")  # 向量化相除

    def roe(self) -> pd.Series:                           # 股東權益報酬率
        """
        ROE = 淨利 / 平均股東權益。季報採 TTM 淨利並以期初期末平均權益，降低季節性影響。
        """
        net = self._ttm(self._series(self.income, "稅後淨利"), "稅後淨利")  # （季報 TTM）淨利
        equity = self._series(self.balance, "股東權益")    # 股東權益（存量）
        avg_equity = (equity + equity.shift(self.lag)) / 2  # 期初期末平均權益（向量化）
        avg_equity = avg_equity.fillna(equity)            # 期初不足時退回當期權益
        return net / avg_equity                           # 向量化相除得 ROE

    def roa(self) -> pd.Series:                           # 資產報酬率
        """ROA = 淨利 / 平均資產總額。季報採 TTM 淨利並以平均資產降低季節性影響。"""  # 方法說明
        net = self._ttm(self._series(self.income, "稅後淨利"), "稅後淨利")  # （季報 TTM）淨利
        assets = self._series(self.balance, "資產總額")    # 資產總額（存量）
        avg_assets = (assets + assets.shift(self.lag)) / 2  # 平均資產（向量化）
        avg_assets = avg_assets.fillna(assets)            # 期初不足時退回當期資產
        return net / avg_assets                           # 向量化相除得 ROA

    # ------------------------------------------------------------------
    # 2. 每股與評價指標（EPS / PER / PBR / PEG）
    # ------------------------------------------------------------------

    def eps(self) -> pd.Series:                           # 每股盈餘
        """
        EPS：優先採用財報的「基本每股盈餘」；若無則以（TTM）淨利 / 流通股數推算。
        """
        eps_row = self._series(self.income, "基本每股盈餘")  # 先取財報 EPS
        if not eps_row.empty:                             # 若財報有提供
            if self.freq == "quarterly":                  # 季報情況
                return eps_row.rolling(4, min_periods=4).sum()  # 以近四季加總為 TTM EPS
            return eps_row                                # 年報直接回傳
        shares = self._shares()                           # 取得流通股數
        if not shares:                                    # 若無股數
            return pd.Series(dtype="float64")             # 無法計算，回傳空
        net = self._ttm(self._series(self.income, "稅後淨利"), "稅後淨利")  # （季報 TTM）淨利
        return net / shares                               # 淨利 / 股數 = EPS

    def _shares(self) -> Optional[float]:                 # 取得流通股數
        """從市場資料取得流通股數；若僅有市值與股價則自動換算。"""  # 方法說明
        shares = self.market.get("shares") or self.market.get("shares_outstanding")  # 直接取股數
        if shares:                                        # 若有
            return float(shares)                          # 回傳
        cap = self.market.get("market_cap")               # 取市值
        price = self.market.get("price")                  # 取股價
        if cap and price:                                 # 若兩者皆有
            return safe_divide(cap, price)                # 市值 / 股價 = 股數
        return None                                       # 否則無法取得

    def per(self) -> float:                               # 本益比（評價，採最新值）
        """PER = 目前股價 / 最新 TTM EPS。"""              # 方法說明
        price = self.market.get("price")                  # 取得股價
        eps = self.eps().dropna()                         # 取得 EPS 序列並去除 NaN
        if price is None or eps.empty:                    # 若缺股價或 EPS
            return 0.0                                     # 回傳 0
        return float(safe_divide(price, eps.iloc[-1]))    # 股價 / 最新 EPS

    def bvps(self) -> pd.Series:                          # 每股淨值
        """每股淨值 BVPS = 股東權益 / 流通股數。"""        # 方法說明
        shares = self._shares()                           # 取得股數
        equity = self._series(self.balance, "股東權益")    # 取得股東權益序列
        if not shares or equity.empty:                    # 若缺股數或權益
            return pd.Series(dtype="float64")             # 回傳空
        return equity / shares                            # 向量化相除

    def pbr(self) -> float:                               # 股價淨值比（評價，採最新值）
        """PBR = 目前股價 / 最新每股淨值。"""              # 方法說明
        price = self.market.get("price")                  # 取得股價
        bvps = self.bvps().dropna()                       # 取得 BVPS 序列
        if price is None or bvps.empty:                   # 若缺股價或 BVPS
            return 0.0                                     # 回傳 0
        return float(safe_divide(price, bvps.iloc[-1]))   # 股價 / 最新 BVPS

    def peg(self) -> float:                               # 本益成長比（評價，採最新值）
        """PEG = PER / 盈餘年成長率(%)。PEG < 1 通常代表成長性相對被低估。"""  # 方法說明
        per = self.per()                                  # 取得 PER
        eps_growth = self.growth("基本每股盈餘", "yoy").dropna()  # 以財報 EPS 年增率為成長率
        if eps_growth.empty:                              # 若無財報 EPS 成長率
            net_growth = self.growth("稅後淨利", "yoy").dropna()  # 改用淨利年增率
            growth_pct = net_growth.iloc[-1] * 100 if not net_growth.empty else 0.0  # 轉百分比
        else:                                             # 有 EPS 成長率
            growth_pct = eps_growth.iloc[-1] * 100        # 轉百分比
        if per <= 0 or growth_pct <= 0:                   # 若 PER 或成長率非正（PEG 無意義）
            return 0.0                                     # 回傳 0
        return float(safe_divide(per, growth_pct))        # PER / 成長率(%)

    # ------------------------------------------------------------------
    # 3. 現金流指標（自由現金流 / FCF Yield）
    # ------------------------------------------------------------------

    def free_cash_flow(self) -> pd.Series:                # 自由現金流
        """
        自由現金流 FCF = 營業活動現金流 - 資本支出。
        （yfinance 的資本支出多為負值，故以加總後取等效；無資本支出時改用財報自由現金流欄位。）
        """
        ocf = self._series(self.cashflow, "營業活動現金流")  # 營業活動現金流
        capex = self._series(self.cashflow, "資本支出")     # 資本支出
        if not ocf.empty and not capex.empty:             # 若兩者皆有
            fcf = ocf + capex.where(capex < 0, -capex)    # 資本支出為負則直接加、為正則扣除
            return self._ttm(fcf, "自由現金流")            # 季報做 TTM 平滑
        fcf_row = self._series(self.cashflow, "自由現金流")  # 退而取財報自由現金流欄位
        return self._ttm(fcf_row, "自由現金流")            # 季報做 TTM 平滑

    def fcf_yield(self) -> float:                         # 自由現金流殖利率（評價，採最新值）
        """FCF Yield = 最新 TTM 自由現金流 / 市值。"""     # 方法說明
        fcf = self.free_cash_flow().dropna()              # 取得 FCF 序列
        cap = self.market.get("market_cap")               # 取得市值
        if fcf.empty or not cap:                          # 若缺 FCF 或市值
            return 0.0                                     # 回傳 0
        return float(safe_divide(fcf.iloc[-1], cap))      # FCF / 市值

    # ------------------------------------------------------------------
    # 4. 償債與流動性指標（負債比率 / 流動比率）
    # ------------------------------------------------------------------

    def debt_ratio(self) -> pd.Series:                    # 負債比率
        """負債比率 = 負債總額 / 資產總額。"""             # 方法說明
        return self._series(self.balance, "負債總額") / self._series(self.balance, "資產總額")  # 向量化

    def current_ratio(self) -> pd.Series:                 # 流動比率
        """流動比率 = 流動資產 / 流動負債，衡量短期償債能力。"""  # 方法說明
        return self._series(self.balance, "流動資產") / self._series(self.balance, "流動負債")  # 向量化

    def equity_ratio(self) -> pd.Series:                  # 權益比率
        """權益比率 = 股東權益 / 資產總額。"""             # 方法說明
        return self._series(self.balance, "股東權益") / self._series(self.balance, "資產總額")  # 向量化

    # ------------------------------------------------------------------
    # 彙總輸出
    # ------------------------------------------------------------------

    def ratio_trends(self) -> pd.DataFrame:               # 各期比率趨勢表
        """彙整逐期的獲利能力與償債指標為一張 DataFrame（向量化組裝）。"""  # 方法說明
        data = {                                          # 組裝各比率序列
            "毛利率": self.gross_margin(),                 # 毛利率
            "營業利益率": self.operating_margin(),         # 營業利益率
            "淨利率": self.net_margin(),                   # 淨利率
            "ROE": self.roe(),                            # 股東權益報酬率
            "ROA": self.roa(),                            # 資產報酬率
            "負債比率": self.debt_ratio(),                 # 負債比率
            "流動比率": self.current_ratio(),              # 流動比率
        }
        df = pd.DataFrame(data)                            # 以期間為索引組成表格
        return df.sort_index()                             # 依期間由舊到新排序

    def summary(self) -> Dict[str, Any]:                  # 最新一期關鍵指標摘要
        """回傳最新一期的關鍵財務與評價指標，方便畫面或 AI 使用。"""  # 方法說明
        def last(s: pd.Series):                           # 取序列最新有效值的小工具
            s = s.dropna()                                # 去除 NaN
            return float(s.iloc[-1]) if not s.empty else None  # 回傳最新值或 None
        return {                                          # 組裝摘要字典
            "毛利率": last(self.gross_margin()),           # 最新毛利率
            "營業利益率": last(self.operating_margin()),   # 最新營業利益率
            "淨利率": last(self.net_margin()),             # 最新淨利率
            "ROE": last(self.roe()),                      # 最新 ROE
            "ROA": last(self.roa()),                      # 最新 ROA
            "EPS": last(self.eps()),                      # 最新 EPS
            "PER": self.per(),                            # 本益比
            "PBR": self.pbr(),                            # 股價淨值比
            "PEG": self.peg(),                            # 本益成長比
            "自由現金流": last(self.free_cash_flow()),     # 最新自由現金流
            "FCF殖利率": self.fcf_yield(),                 # 自由現金流殖利率
            "負債比率": last(self.debt_ratio()),           # 最新負債比率
            "流動比率": last(self.current_ratio()),        # 最新流動比率
            "營收年增率": last(self.growth("營業收入", "yoy")),  # 最新營收 YoY
            "淨利年增率": last(self.growth("稅後淨利", "yoy")),  # 最新淨利 YoY
        }

    def to_record(self, code: str, name: str = None) -> Dict[str, Any]:
        """
        將最新一期指標轉為「選股器可直接使用」的紀錄格式（英文鍵 + 額外進階指標）。
        讓 FinancialMetrics 的計算結果能無縫餵給 StockScreener。
        """
        s = self.summary()                                # 取得最新一期指標摘要
        return {                                          # 組裝選股器格式的紀錄
            "code": str(code),                            # 股票代號
            "name": name or str(code),                    # 公司名稱
            "roe": s["ROE"],                              # ROE
            "roa": s["ROA"],                              # ROA
            "pe": s["PER"],                               # 本益比
            "pb": s["PBR"],                               # 股價淨值比
            "peg": s["PEG"],                              # 本益成長比
            "eps": s["EPS"],                              # 每股盈餘
            "debt_ratio": s["負債比率"],                   # 負債比率
            "gross_margin": s["毛利率"],                   # 毛利率
            "operating_margin": s["營業利益率"],           # 營業利益率
            "net_margin": s["淨利率"],                     # 淨利率
            "current_ratio": s["流動比率"],                # 流動比率
            "fcf_yield": s["FCF殖利率"],                   # 自由現金流殖利率
            "revenue_yoy": s["營收年增率"],                # 營收年增率
            "dividend_yield": self.market.get("dividend_yield"),  # 殖利率（沿用市場資料）
        }


if __name__ == "__main__":                                # 直接執行此檔的簡易示範
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 確保可匯入資料套件
    from data.fetcher import StockFetcher                  # 匯入擷取器取得合成資料
    fetcher = StockFetcher()                                # 建立擷取器
    df = fetcher.generate_sample_price("2330")              # 產生合成股價
    analyzer = QuantAnalyzer(df)                            # 建立量化分析器
    print("=== 價格量化指標 ===")                          # 標題
    print(analyzer.summary())                              # 印出價格類量化指標
    stmts = fetcher.get_financial_statements("2330")        # 取得三大報表
    print("\n=== 財務比率趨勢 ===")                        # 標題
    print(financial_ratio_trends(stmts))                   # 印出簡易比率趨勢
    market = fetcher.fetch_financials("2330")               # 取得市場與基本面資料
    metrics = FinancialMetrics(stmts, freq="annual", market=market)  # 建立財務指標計算器
    print("\n=== 台股財務指標摘要 ===")                    # 標題
    for k, v in metrics.summary().items():                 # 逐項印出指標摘要
        print(f"{k}: {v}")                                # 印出指標名稱與數值
