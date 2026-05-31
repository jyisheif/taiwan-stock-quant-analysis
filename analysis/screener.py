# -*- coding: utf-8 -*-
"""
analysis/screener.py
選股篩選模組：提供多條件篩選與「可插拔策略」架構的 StockScreener。

設計理念（易於擴充新策略）：
  - 以 `Strategy` 抽象基底類別定義策略介面（passes 過濾 + score_one 打分 + evaluate 批次）。
  - 透過 `@register_strategy("名稱")` 裝飾器將新策略自動註冊到 `STRATEGY_REGISTRY`，
    要新增策略只需「定義一個類別 + 加一行裝飾器」，不需改動 StockScreener。
  - StockScreener 負責編排：套用硬性條件過濾，再以選定策略打分排序。

內建策略：
  - value          價值型（低 PE / 低 PB / 高殖利率）
  - growth         成長型（高營收成長 / 高 ROE / 高淨利率）
  - quality        品質型（高 ROE / 高毛利 / 低負債 / 正自由現金流）
  - magic_formula  魔法公式（盈餘殖利率 + 資本報酬率 排名合併）
  - piotroski      Piotroski F-Score（9 項財務健康度指標）
"""

from __future__ import annotations                        # 啟用延遲型別評估

import os                                                 # 匯入 os 處理路徑
import sys                                                # 匯入 sys 調整搜尋路徑
import abc                                                # 匯入 abc 以定義抽象基底類別
from typing import List, Dict, Optional, Union            # 匯入型別註記工具

import pandas as pd                                       # 匯入 pandas 處理表格資料

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

from config import settings                               # 匯入全域設定（篩選門檻）


# =====================================================================
# 工具函式
# =====================================================================

def _num(rec: Dict, key: str, default: float = 0.0) -> float:
    """安全地從紀錄取出數值欄位；缺值或無法轉換時回傳預設值。"""  # 函式說明
    val = rec.get(key)                                    # 取出欄位值
    if val is None:                                       # 若為 None
        return default                                    # 回傳預設值
    try:                                                  # 嘗試轉為浮點數
        return float(val)                                 # 回傳數值
    except (TypeError, ValueError):                       # 若無法轉換
        return default                                    # 回傳預設值


# =====================================================================
# 策略架構：抽象基底 + 註冊表 + 裝飾器
# =====================================================================

STRATEGY_REGISTRY: Dict[str, type] = {}                   # 策略註冊表（名稱 -> 類別）


def register_strategy(name: str):                         # 策略註冊裝飾器
    """
    類別裝飾器：將策略類別以指定名稱註冊到全域註冊表。
    新增策略時只需在類別上方加一行 @register_strategy("名稱")。
    """
    def decorator(cls):                                   # 實際的裝飾函式
        cls.name = name                                   # 將名稱寫入類別屬性
        STRATEGY_REGISTRY[name] = cls                     # 登錄到註冊表
        return cls                                        # 回傳原類別
    return decorator                                      # 回傳裝飾器


class Strategy(abc.ABC):                                   # 策略抽象基底類別
    """
    選股策略介面。子類別至少需實作 score_one()（單檔打分）；
    若策略需要跨股票排名（如魔法公式），可改為覆寫 evaluate()。
    """

    name: str = "base"                                    # 策略識別名稱
    description: str = ""                                 # 策略說明（顯示用）

    def passes(self, rec: Dict) -> bool:                  # 策略層級的可選硬性條件
        """策略自有的過濾條件，預設不過濾（全部通過）。"""    # 方法說明
        return True                                       # 預設通過

    def score_one(self, rec: Dict) -> float:              # 單檔打分（多數策略覆寫此處）
        """對單一股票計算策略分數，分數越高越符合策略。"""    # 方法說明
        return 0.0                                        # 預設為 0

    def evaluate(self, records: List[Dict]) -> pd.DataFrame:  # 批次評估（可被覆寫）
        """
        對一籃子股票套用策略：過濾 -> 打分 -> 依分數排序。
        需要跨股票排名的策略（如魔法公式）會覆寫此方法。
        """
        rows = []                                         # 收集通過策略過濾的股票
        for rec in records:                               # 逐一處理
            if not self.passes(rec):                      # 若未通過策略過濾
                continue                                  # 略過
            row = dict(rec)                               # 複製紀錄
            row["score"] = round(float(self.score_one(rec)), 4)  # 加上策略分數
            rows.append(row)                              # 收集
        df = pd.DataFrame(rows)                           # 轉為 DataFrame
        if not df.empty:                                  # 若有資料
            df = df.sort_values("score", ascending=False).reset_index(drop=True)  # 依分數排序
        return df                                         # 回傳結果


# =====================================================================
# 內建策略實作
# =====================================================================

@register_strategy("value")                               # 註冊為「價值型」
class ValueStrategy(Strategy):                             # 價值型策略
    """價值型：偏好低本益比、低股價淨值比、高殖利率。"""    # 策略說明
    description = "價值型（低 PE / 低 PB / 高殖利率）"      # 顯示用說明

    def passes(self, rec: Dict) -> bool:                  # 過濾條件
        return _num(rec, "pe", 0) > 0                     # 本益比須為正（排除虧損股）

    def score_one(self, rec: Dict) -> float:              # 打分
        pe = _num(rec, "pe", 0)                           # 本益比
        pb = _num(rec, "pb", 0)                           # 股價淨值比
        dy = _num(rec, "dividend_yield", 0)               # 殖利率
        earnings_yield = (1 / pe) if pe > 0 else 0        # 盈餘殖利率（本益比倒數）
        book_yield = (1 / pb) if pb > 0 else 0            # 淨值殖利率（淨值比倒數）
        return earnings_yield * 100 + book_yield * 20 + dy * 100  # 加權合計（越低估分數越高）


@register_strategy("growth")                              # 註冊為「成長型」
class GrowthStrategy(Strategy):                           # 成長型策略
    """成長型：偏好高營收成長、高 ROE、高淨利率。"""        # 策略說明
    description = "成長型（高營收成長 / 高 ROE / 高淨利率）"  # 顯示用說明

    def passes(self, rec: Dict) -> bool:                  # 過濾條件
        return rec.get("revenue_yoy") is not None         # 需有營收成長率資料

    def score_one(self, rec: Dict) -> float:              # 打分
        growth = _num(rec, "revenue_yoy", 0)              # 營收年增率
        roe = _num(rec, "roe", 0)                         # ROE
        net_margin = _num(rec, "net_margin", 0)           # 淨利率
        return growth * 100 + roe * 60 + net_margin * 40  # 加權合計（成長性越強分數越高）


@register_strategy("quality")                             # 註冊為「品質型」
class QualityStrategy(Strategy):                          # 品質型策略
    """品質型：偏好高 ROE、高毛利、低負債、正自由現金流。"""  # 策略說明
    description = "品質型（高 ROE / 高毛利 / 低負債 / 正 FCF）"  # 顯示用說明

    def score_one(self, rec: Dict) -> float:              # 打分
        roe = _num(rec, "roe", 0)                         # ROE
        gross_margin = _num(rec, "gross_margin", 0)       # 毛利率
        current_ratio = _num(rec, "current_ratio", 0)     # 流動比率
        fcf_yield = _num(rec, "fcf_yield", 0)             # 自由現金流殖利率
        debt_ratio = _num(rec, "debt_ratio", 0)           # 負債比率
        return (                                          # 加權合計
            roe * 100                                     # ROE 越高越好
            + gross_margin * 50                           # 毛利率越高越好
            + current_ratio * 10                          # 流動比率越高越好
            + fcf_yield * 100                             # 自由現金流殖利率越高越好
            - debt_ratio * 50                             # 負債比率越高扣分
        )


@register_strategy("magic_formula")                       # 註冊為「魔法公式」
class MagicFormulaStrategy(Strategy):                     # 魔法公式策略（Greenblatt）
    """
    魔法公式：分別以「盈餘殖利率」與「資本報酬率」對全體股票排名，
    再合併兩個排名（名次和越小越好），藉此挑出又便宜又賺錢的好公司。
    """
    description = "魔法公式（盈餘殖利率 + 資本報酬率 排名）"  # 顯示用說明

    def evaluate(self, records: List[Dict]) -> pd.DataFrame:  # 覆寫批次評估（需跨股票排名）
        df = pd.DataFrame([dict(r) for r in records])     # 轉為 DataFrame
        if df.empty:                                      # 若無資料
            return df                                     # 回傳空表
        pe = df["pe"] if "pe" in df else pd.Series([0] * len(df))  # 取本益比欄位
        df["earnings_yield"] = pe.apply(                  # 盈餘殖利率 = 1 / 本益比
            lambda x: (1.0 / x) if (pd.notna(x) and x > 0) else 0.0
        )
        roa = df["roa"] if "roa" in df else pd.Series([None] * len(df))  # 取 ROA
        roe = df["roe"] if "roe" in df else pd.Series([None] * len(df))  # 取 ROE
        df["roc"] = [                                     # 資本報酬率：優先用 ROA，否則退回 ROE
            (a if (a is not None and a > 0) else (b if b is not None else 0.0))
            for a, b in zip(roa, roe)
        ]
        ey_rank = df["earnings_yield"].rank(ascending=False, method="min")  # 盈餘殖利率名次（高者佳）
        roc_rank = df["roc"].rank(ascending=False, method="min")  # 資本報酬率名次（高者佳）
        df["mf_combined"] = ey_rank + roc_rank            # 合併名次（越小越好）
        df = df.sort_values("mf_combined").reset_index(drop=True)  # 依合併名次排序
        df["score"] = (df["mf_combined"].max() + 1) - df["mf_combined"]  # 轉為分數（越高越好）
        df["score"] = df["score"].round(4)               # 四捨五入
        return df                                         # 回傳排名結果


@register_strategy("piotroski")                           # 註冊為「Piotroski F-Score」
class PiotroskiFScoreStrategy(Strategy):                  # Piotroski F-Score 策略
    """
    Piotroski F-Score：以 9 項二元（0/1）財務健康度訊號加總，分數 0~9，越高越健康。
    需要當期與「上期」資料才能評估趨勢類訊號；上期資料以紀錄中的 'prev' 子字典提供，
    缺乏對應資料的訊號該分不計（保守處理）。
    """
    description = "Piotroski F-Score（9 項財務健康度，0~9 分）"  # 顯示用說明

    @staticmethod                                          # 靜態方法
    def fscore(rec: Dict) -> tuple:                       # 計算 F-Score 與各項明細
        """回傳 (總分, 各項訊號明細 dict)。"""              # 方法說明
        prev = rec.get("prev") or {}                      # 取得上期資料（可能為空）
        detail: Dict[str, int] = {}                       # 各項訊號的得分明細

        roa = rec.get("roa")                              # 當期 ROA
        cfo = rec.get("operating_cf")                     # 當期營業現金流
        ni = rec.get("net_income")                        # 當期淨利

        # --- 獲利能力（4 項）---
        detail["ROA為正"] = int(roa is not None and roa > 0)  # 1) ROA > 0
        detail["營業現金流為正"] = int(cfo is not None and cfo > 0)  # 2) 營業現金流 > 0
        detail["ROA較上期提升"] = int(                     # 3) ROA 較上期提升
            roa is not None and prev.get("roa") is not None and roa > prev["roa"]
        )
        detail["盈餘品質(CFO>淨利)"] = int(                # 4) 營業現金流 > 淨利（應計品質）
            cfo is not None and ni is not None and cfo > ni
        )

        # --- 財務槓桿與流動性（3 項）---
        dr, dr_p = rec.get("debt_ratio"), prev.get("debt_ratio")  # 負債比（當期/上期）
        detail["負債比下降"] = int(dr is not None and dr_p is not None and dr < dr_p)  # 5) 負債比下降
        cr, cr_p = rec.get("current_ratio"), prev.get("current_ratio")  # 流動比（當期/上期）
        detail["流動比上升"] = int(cr is not None and cr_p is not None and cr > cr_p)  # 6) 流動比上升
        sh, sh_p = rec.get("shares"), prev.get("shares")  # 流通股數（當期/上期）
        detail["未發行新股稀釋"] = int(sh is not None and sh_p is not None and sh <= sh_p)  # 7) 未增資

        # --- 營運效率（2 項）---
        gm, gm_p = rec.get("gross_margin"), prev.get("gross_margin")  # 毛利率（當期/上期）
        detail["毛利率上升"] = int(gm is not None and gm_p is not None and gm > gm_p)  # 8) 毛利率上升
        at, at_p = rec.get("asset_turnover"), prev.get("asset_turnover")  # 資產周轉率（當期/上期）
        detail["資產周轉率上升"] = int(at is not None and at_p is not None and at > at_p)  # 9) 周轉率上升

        return sum(detail.values()), detail               # 回傳總分與明細

    def score_one(self, rec: Dict) -> float:              # 打分（即 F-Score 總分）
        score, _ = self.fscore(rec)                       # 計算 F-Score
        return float(score)                               # 回傳分數

    def evaluate(self, records: List[Dict]) -> pd.DataFrame:  # 覆寫批次評估（附帶 fscore 欄位）
        rows = []                                         # 收集結果
        for rec in records:                               # 逐一處理
            if not self.passes(rec):                      # 若未通過策略過濾
                continue                                  # 略過
            score, _ = self.fscore(rec)                   # 計算 F-Score
            row = dict(rec)                               # 複製紀錄
            row["fscore"] = score                         # 加上 F-Score 欄位
            row["score"] = float(score)                   # 排序分數即 F-Score
            rows.append(row)                              # 收集
        df = pd.DataFrame(rows)                           # 轉為 DataFrame
        if not df.empty:                                  # 若有資料
            df = df.sort_values("score", ascending=False).reset_index(drop=True)  # 依分數排序
        return df                                         # 回傳結果


# =====================================================================
# 選股器：編排「硬性條件過濾」與「策略打分排序」
# =====================================================================

class StockScreener:                                       # 選股篩選類別
    """
    選股器：結合多條件硬性過濾與可插拔策略打分。

    使用方式：
      - 多條件加權（預設）：StockScreener(min_roe=...).screen(records)
      - 套用策略：       StockScreener().screen(records, strategy="value")
      - 取得策略清單：    StockScreener.available_strategies()
    """

    def __init__(                                          # 建構子，可自訂篩選門檻與預設策略
        self,
        min_roe: float = None,                             # ROE 最低門檻
        max_pe: float = None,                              # 本益比上限
        min_eps: float = None,                             # EPS 最低門檻
        max_debt_ratio: float = None,                      # 負債比率上限
        min_gross_margin: float = None,                    # 毛利率最低門檻（進階，None 表不啟用）
        min_current_ratio: float = None,                   # 流動比率最低門檻（進階，None 表不啟用）
        min_fcf_yield: float = None,                       # FCF 殖利率最低門檻（進階，None 表不啟用）
        strategy: Union[str, Strategy, None] = None,       # 預設使用的策略（名稱或物件）
    ):
        self.min_roe = min_roe if min_roe is not None else settings.min_roe  # 未指定時用設定預設值
        self.max_pe = max_pe if max_pe is not None else settings.max_pe      # 本益比上限
        self.min_eps = min_eps if min_eps is not None else settings.min_eps  # EPS 門檻
        self.max_debt_ratio = (                            # 負債比率上限
            max_debt_ratio if max_debt_ratio is not None else settings.max_debt_ratio
        )
        self.min_gross_margin = min_gross_margin           # 毛利率門檻（進階條件）
        self.min_current_ratio = min_current_ratio         # 流動比率門檻（進階條件）
        self.min_fcf_yield = min_fcf_yield                 # FCF 殖利率門檻（進階條件）
        self.strategy = strategy                           # 預設策略

    # ------------------------------------------------------------------
    # 硬性條件過濾與多條件加權打分（預設行為，與舊版相容）
    # ------------------------------------------------------------------

    def passes(self, fin: Dict) -> bool:                  # 判斷單一股票是否通過所有條件
        """檢查一檔股票的財報是否符合所有（含進階）硬性篩選條件。"""  # 方法說明
        roe = fin.get("roe") or 0                          # 取得 ROE（缺值視為 0）
        pe = fin.get("pe") or 9999                          # 取得本益比（缺值視為極大，不利通過）
        eps = fin.get("eps") or 0                           # 取得 EPS（缺值視為 0）
        debt = fin.get("debt_ratio")                        # 取得負債比率（可能為 None）
        debt = debt if debt is not None else 0              # 缺值時視為 0（不擋條件）
        if not (                                            # 先檢查基本四項條件
            roe >= self.min_roe                             # ROE 須達門檻
            and pe <= self.max_pe                           # 本益比須在上限內
            and eps >= self.min_eps                         # EPS 須達門檻
            and debt <= self.max_debt_ratio                 # 負債比率須在上限內
        ):
            return False                                    # 任一不符即淘汰

        # --- 進階條件：僅在有設定門檻時才套用 ---
        if self.min_gross_margin is not None:               # 若有設定毛利率門檻
            if (fin.get("gross_margin") or 0) < self.min_gross_margin:  # 毛利率未達標
                return False                                # 淘汰
        if self.min_current_ratio is not None:              # 若有設定流動比率門檻
            if (fin.get("current_ratio") or 0) < self.min_current_ratio:  # 流動比率未達標
                return False                                # 淘汰
        if self.min_fcf_yield is not None:                  # 若有設定 FCF 殖利率門檻
            if (fin.get("fcf_yield") or 0) < self.min_fcf_yield:  # FCF 殖利率未達標
                return False                                # 淘汰
        return True                                         # 全數通過

    def score(self, fin: Dict) -> float:                   # 多條件加權打分（預設策略）
        """以加權方式計算股票吸引力評分，分數越高越優；自動納入可用的進階指標。"""  # 方法說明
        roe = fin.get("roe") or 0                          # 取得 ROE
        pe = fin.get("pe") or 9999                          # 取得本益比
        eps = fin.get("eps") or 0                           # 取得 EPS
        dy = fin.get("dividend_yield") or 0                 # 取得殖利率
        score = 0.0                                         # 評分初始化
        score += roe * 100                                  # ROE 越高分數越高（乘 100 放大）
        score += max(0, (self.max_pe - pe))                 # 本益比越低（相對上限）分數越高
        score += eps                                        # EPS 直接貢獻分數
        score += dy * 50                                    # 殖利率貢獻分數（乘 50 放大）
        # --- 進階指標加分（若資料存在則納入）---
        score += (fin.get("gross_margin") or 0) * 30        # 毛利率加分
        score += (fin.get("net_margin") or 0) * 30          # 淨利率加分
        score += (fin.get("fcf_yield") or 0) * 100          # FCF 殖利率加分
        score += (fin.get("revenue_yoy") or 0) * 20         # 營收年增率加分
        return round(score, 2)                              # 回傳四捨五入後的評分

    # ------------------------------------------------------------------
    # 策略編排
    # ------------------------------------------------------------------

    @staticmethod                                          # 靜態方法
    def available_strategies() -> Dict[str, str]:         # 取得可用策略清單
        """回傳所有已註冊策略的 {名稱: 說明}，方便 UI 動態列出。"""  # 方法說明
        return {name: getattr(cls, "description", "") for name, cls in STRATEGY_REGISTRY.items()}  # 組裝字典

    @staticmethod                                          # 靜態方法
    def _resolve_strategy(strategy: Union[str, Strategy, None]) -> Optional[Strategy]:
        """將策略名稱或物件解析為策略實例；None 表示使用預設多條件打分。"""  # 方法說明
        if strategy is None:                              # 若未指定
            return None                                   # 回傳 None（用預設打分）
        if isinstance(strategy, Strategy):                # 若已是策略物件
            return strategy                               # 直接使用
        if isinstance(strategy, str):                     # 若為名稱字串
            cls = STRATEGY_REGISTRY.get(strategy)         # 從註冊表查找
            if cls is None:                               # 若查無此策略
                raise ValueError(f"未知的策略：{strategy}，可用策略：{list(STRATEGY_REGISTRY)}")  # 拋錯
            return cls()                                  # 建立並回傳策略實例
        raise TypeError("strategy 需為策略名稱字串或 Strategy 物件")  # 型別錯誤

    def screen(                                            # 執行選股
        self,
        financials_list: List[Dict],                      # 一籃子股票的指標紀錄
        strategy: Union[str, Strategy, None] = None,      # 本次使用的策略（覆寫預設）
        apply_filter: bool = True,                         # 是否先套用硬性條件過濾
        top_n: Optional[int] = None,                      # 只取前 N 名（None 表全部）
    ) -> pd.DataFrame:
        """
        對多檔股票進行選股：
          1.（可選）先以硬性條件過濾，
          2. 以選定策略（或預設多條件加權）打分並排序，
          3.（可選）取前 N 名。
        回傳含 score 欄位、依分數由高到低排序的 DataFrame。
        """
        strat = self._resolve_strategy(strategy if strategy is not None else self.strategy)  # 解析策略
        recs = [r for r in financials_list if (self.passes(r) if apply_filter else True)]  # 套用硬性過濾

        if strat is None:                                 # 若無策略（預設多條件加權）
            rows = []                                      # 收集結果
            for rec in recs:                               # 逐一打分
                row = dict(rec)                            # 複製紀錄
                row["score"] = self.score(rec)             # 加上加權分數
                rows.append(row)                           # 收集
            df = pd.DataFrame(rows)                         # 轉為 DataFrame
            if not df.empty:                               # 若有資料
                df = df.sort_values("score", ascending=False).reset_index(drop=True)  # 依分數排序
        else:                                             # 若指定策略
            df = strat.evaluate(recs)                      # 交由策略批次評估

        if top_n is not None and not df.empty:            # 若限制名次
            df = df.head(top_n).reset_index(drop=True)     # 取前 N 名
        return df                                          # 回傳選股結果

    # ------------------------------------------------------------------
    # 與 FinancialMetrics 整合：直接由時間序列計算 Piotroski F-Score
    # ------------------------------------------------------------------

    @staticmethod                                          # 靜態方法
    def fscore_from_metrics(metrics) -> tuple:            # 由 FinancialMetrics 計算 F-Score
        """
        利用 FinancialMetrics 的時間序列，自動組出當期與上期資料並計算 Piotroski F-Score。
        回傳 (總分, 各項明細 dict)。
        """
        income, balance, cashflow = metrics.income, metrics.balance, metrics.cashflow  # 三大報表
        series = metrics._series                          # 取序列的內部工具

        def last_two(s: pd.Series):                       # 取序列最新兩期值
            """回傳 (最新值, 上期值)，不足時以 None 補。"""  # 內部說明
            s = s.dropna()                                # 去除缺值
            if len(s) >= 2:                               # 至少兩期
                return float(s.iloc[-1]), float(s.iloc[-2])  # 回傳最新與上期
            if len(s) == 1:                               # 只有一期
                return float(s.iloc[-1]), None            # 上期以 None 表示
            return None, None                             # 無資料

        roa_c, roa_p = last_two(metrics.roa())            # ROA 當期/上期
        gm_c, gm_p = last_two(metrics.gross_margin())     # 毛利率 當期/上期
        cr_c, cr_p = last_two(metrics.current_ratio())    # 流動比 當期/上期
        dr_c, dr_p = last_two(metrics.debt_ratio())       # 負債比 當期/上期
        at_series = series(income, "營業收入") / series(balance, "資產總額")  # 資產周轉率序列
        at_c, at_p = last_two(at_series)                  # 資產周轉率 當期/上期
        cfo_c, _ = last_two(series(cashflow, "營業活動現金流"))  # 營業現金流（當期）
        ni_c, _ = last_two(metrics._ttm(series(income, "稅後淨利"), "稅後淨利"))  # 淨利（當期, 季報 TTM）

        rec = {                                           # 組裝 F-Score 所需紀錄
            "roa": roa_c, "operating_cf": cfo_c, "net_income": ni_c,  # 獲利能力相關
            "gross_margin": gm_c, "current_ratio": cr_c,             # 效率/流動性
            "debt_ratio": dr_c, "asset_turnover": at_c,              # 槓桿/周轉
            "prev": {                                     # 上期資料（供趨勢類訊號比較）
                "roa": roa_p, "gross_margin": gm_p, "current_ratio": cr_p,
                "debt_ratio": dr_p, "asset_turnover": at_p,
            },
        }
        return PiotroskiFScoreStrategy.fscore(rec)        # 計算並回傳 F-Score


if __name__ == "__main__":                                # 直接執行此檔的簡易示範
    from data.fetcher import StockFetcher                  # 匯入擷取器以產生合成財報
    fetcher = StockFetcher()                                # 建立擷取器
    pool = [fetcher.generate_sample_financials(c)           # 產生一籃子合成財報
            for c in ["2330", "2317", "2454", "2603", "1101"]]
    print("可用策略：", StockScreener().available_strategies())  # 印出可用策略
    for strat_name in ["value", "growth", "quality", "magic_formula"]:  # 逐一示範各策略
        res = StockScreener().screen(pool, strategy=strat_name, apply_filter=False, top_n=3)  # 執行策略選股
        cols = [c for c in ["code", "roe", "pe", "score"] if c in res.columns]  # 顯示欄位
        print(f"\n=== 策略：{strat_name} (前3名) ===")      # 標題
        print(res[cols] if not res.empty else "（無結果）")  # 印出結果
