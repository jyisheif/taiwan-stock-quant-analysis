# -*- coding: utf-8 -*-
"""
ai/analyst.py
AI 投資分析模組：扮演專業台股分析師，綜合「財報、估值、成長、技術面、風險」五大面向，
透過 OpenAI Structured Output（結構化輸出 / JSON Mode）產出一份結構化的投資結論
（買入/賣出建議、評分、信心、目標價、潛在漲幅、風險等級、關鍵理由、總結）。

設計重點：
  - 以 Pydantic 模型 `AnalysisResult` 嚴格定義輸出結構，並對 AI 回傳值做驗證與夾限（clamp）。
  - 主力路徑使用 OpenAI 結構化輸出；無金鑰或呼叫失敗時，退回「本地規則式」推論，
    仍回傳同一個 `AnalysisResult` 結構，確保離線與測試皆可運作。
  - 保留舊版 `AIAnalyst.analyze()`（回傳純文字）以維持既有相容性。
"""

from __future__ import annotations                        # 啟用延遲型別評估

import os                                                 # 匯入 os 處理路徑與環境變數
import sys                                                # 匯入 sys 調整搜尋路徑
from typing import Dict, Optional, List, Literal, Any     # 匯入型別註記工具

from pydantic import BaseModel, Field, model_validator    # 匯入 Pydantic 以定義並驗證結構化結果

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 將專案根目錄加入搜尋路徑

from config import settings                               # 匯入全域設定（API 金鑰、模型名稱）
from utils.helpers import format_percent, format_number   # 匯入格式化工具


# =====================================================================
# 結構化分析結果模型（Pydantic）
# =====================================================================

class AnalysisResult(BaseModel):
    """AI 台股分析的結構化結果；同時作為 OpenAI 結構化輸出的回應綱要（schema）。"""

    recommendation: Literal["強力買入", "買入", "持有", "賣出", "強力賣出"] = Field(  # 投資建議
        description="綜合評估後的操作建議，必須是五個選項之一。"
    )
    score: int = Field(                                   # 綜合評分
        description="綜合評分，範圍 -10（強力賣出）到 +10（強力買入），整數。"
    )
    confidence: float = Field(                            # 信心水準
        description="對此結論的信心水準，範圍 0 到 100。"
    )
    target_price: Optional[float] = Field(                # 目標價
        default=None, description="十二個月目標價；若資料不足無法估算則為 null。"
    )
    upside_potential: Optional[float] = Field(            # 潛在漲幅
        default=None, description="相對目前股價的潛在漲跌幅（百分比，可為負）；無法估算則為 null。"
    )
    risk_level: Literal["低", "中", "高"] = Field(         # 風險等級
        description="整體投資風險等級，必須是 低 / 中 / 高 之一。"
    )
    key_reasons: List[str] = Field(                       # 關鍵理由
        description="支持此建議的 3 到 6 條關鍵理由，每條為簡短繁體中文句子。"
    )
    summary: str = Field(                                 # 總結
        description="200 字以內的繁體中文投資總結，客觀說明立論與風險。"
    )

    @model_validator(mode="after")                        # 解析後驗證器（不影響送往 OpenAI 的綱要）
    def _clamp_ranges(self) -> "AnalysisResult":          # 將數值夾限在合理範圍
        """確保分數與信心落在規定範圍，避免模型偶發越界。"""  # 方法說明
        self.score = int(max(-10, min(10, self.score)))   # 分數夾限於 -10 ~ 10
        self.confidence = float(max(0.0, min(100.0, self.confidence)))  # 信心夾限於 0 ~ 100
        return self                                       # 回傳自身


# =====================================================================
# System Prompt：專業台股分析師角色
# =====================================================================

SYSTEM_PROMPT = """\
你是一位擁有 CFA 證照、深耕台灣股市（TWSE / TPEx）逾十五年的資深證券分析師，
專長為基本面與量化分析並重的價值投資。你的任務是針對單一台股個股，
綜合下列五大面向做出客觀、可執行的投資判斷：

1. 財報基本面：獲利能力（ROE、ROA、毛利率、淨利率）、財務結構（負債比、流動比）、每股盈餘。
2. 估值水準：本益比、股價淨值比、合理價與目前股價的折溢價、相對歷史與同業的位置。
3. 成長動能：營收年增率、獲利成長、趨勢延續性與動能轉折。
4. 技術面：價格趨勢、年化報酬、波動度、夏普比率、最大回撤、RSI 超買超賣。
5. 風險：財務槓桿、現金流品質、產業景氣循環、波動度與下檔風險。

判斷與輸出原則：
- 以繁體中文回答，立場中立，避免投機性誇大用語。
- score 必須是 -10 到 +10 的整數：+6~+10 對應「強力買入」、+2~+5「買入」、
  -1~+1「持有」、-5~-2「賣出」、-10~-6「強力賣出」，且 score 須與 recommendation 一致。
- confidence（0~100）反映資料完整度與各面向訊號的一致性；訊號越分歧、資料越缺，信心越低。
- target_price 為十二個月目標價；若缺乏估值資料則回傳 null。
- upside_potential 為相對目前股價的百分比（可為負）；無法估算則 null。
- risk_level 依財務槓桿與波動度綜合判定為 低 / 中 / 高。
- key_reasons 條列 3~6 點，需橫跨上述面向，言之有據。
- summary 為 200 字內總結。
- 你不對未提供的數據臆測；資料不足時應降低 confidence 並於理由中說明。
- 本分析僅供參考，不構成投資要約。
"""


# =====================================================================
# 提示詞組裝與資料正規化
# =====================================================================

# 各面向標籤與其常見欄位的中文對照（用於組裝提示詞，缺漏欄位會自動略過）
_SECTION_FIELDS = {
    "財報基本面": {
        "name": "公司名稱", "price": "目前股價", "pe": "本益比", "pb": "股價淨值比",
        "eps": "每股盈餘", "roe": "ROE", "roa": "ROA", "gross_margin": "毛利率",
        "operating_margin": "營業利益率", "net_margin": "淨利率",
        "debt_ratio": "負債比率", "current_ratio": "流動比率",
        "dividend_yield": "殖利率", "fcf_yield": "自由現金流殖利率", "market_cap": "市值",
    },
    "估值": {
        "fair_value": "綜合合理價", "current_price": "目前股價",
        "pe_fair_value": "本益比法合理價", "ggm_fair_value": "股利折現法合理價",
        "upside": "潛在漲幅",
    },
    "成長性": {
        "revenue_yoy": "營收年增率", "net_yoy": "淨利年增率",
        "eps_yoy": "EPS 年增率", "revenue_qoq": "營收季增率",
    },
    "技術面": {
        "annual_return": "年化報酬率", "annual_volatility": "年化波動率",
        "sharpe_ratio": "夏普比率", "max_drawdown": "最大回撤", "rsi": "RSI",
    },
    "風險": {
        "debt_ratio": "負債比率", "beta": "Beta 係數",
        "volatility": "波動度", "max_drawdown": "最大回撤",
    },
}

# 以百分比顯示的欄位（其餘以一般數字顯示）
_PERCENT_FIELDS = {
    "roe", "roa", "gross_margin", "operating_margin", "net_margin", "debt_ratio",
    "dividend_yield", "fcf_yield", "upside", "revenue_yoy", "net_yoy", "eps_yoy",
    "revenue_qoq", "annual_return", "annual_volatility", "max_drawdown", "volatility",
}


def _section_data(data: Dict[str, Any], section_key: str) -> Dict[str, Any]:
    """取得某面向的資料；若 data 為扁平結構（無分區），則回傳整體 data。"""  # 函式說明
    if any(k in data for k in ("financials", "valuation", "growth", "technical", "risk")):  # 有分區
        mapping = {                                       # 面向標籤對 data 的鍵
            "財報基本面": "financials", "估值": "valuation", "成長性": "growth",
            "技術面": "technical", "風險": "risk",
        }
        return data.get(mapping.get(section_key, ""), {}) or {}  # 回傳該分區（缺則空）
    return data                                           # 扁平結構：所有面向共用同一份資料


def _fmt(field: str, value: Any) -> str:
    """依欄位性質將數值格式化為百分比或一般數字字串。"""  # 函式說明
    if isinstance(value, (int, float)):                   # 數值型
        return format_percent(value) if field in _PERCENT_FIELDS else format_number(value)  # 百分比或數字
    return str(value)                                     # 其餘直接轉字串


def build_analysis_prompt(stock_code: str, data: Dict[str, Any]) -> str:
    """將個股各面向資料組裝為提供給 AI 的使用者提示詞。"""  # 函式說明
    lines = [f"請分析台股代號 {stock_code} 的投資價值。以下為已蒐集之資料："]  # 開場
    for section, fields in _SECTION_FIELDS.items():       # 逐一面向組裝
        sec_data = _section_data(data, section)           # 取得該面向資料
        rows = [                                          # 收集該面向有值的欄位
            f"  - {label}：{_fmt(key, sec_data.get(key))}"
            for key, label in fields.items()
            if sec_data.get(key) is not None              # 僅列出有資料者
        ]
        if rows:                                          # 若該面向有資料
            lines.append(f"【{section}】")                # 面向標題
            lines.extend(rows)                            # 加入欄位明細
    lines.append("請依系統指示，輸出結構化的投資分析結果。")  # 結尾要求
    return "\n".join(lines)                               # 串接為完整提示詞


# =====================================================================
# 核心函式：取得 AI 結構化分析
# =====================================================================

def get_ai_analysis(
    stock_code: str,                                      # 股票代號
    data: Dict[str, Any],                                 # 個股各面向資料（可分區或扁平）
    api_key: Optional[str] = None,                        # OpenAI 金鑰（None 時用設定值，"" 強制離線）
    model: Optional[str] = None,                          # 使用的模型名稱
) -> AnalysisResult:
    """
    取得個股的 AI 結構化投資分析。
    優先使用 OpenAI 結構化輸出；若無金鑰或呼叫失敗，退回本地規則式推論（回傳同型別結果）。
    """
    key = api_key if api_key is not None else settings.openai_api_key  # 決定金鑰（"" 視為無金鑰）
    model = model or settings.openai_model                # 決定模型

    if key:                                               # 若有金鑰
        try:                                              # 嘗試呼叫 OpenAI 結構化輸出
            return _analyze_with_openai(stock_code, data, key, model)  # 回傳 AI 結果
        except Exception:                                 # 任何失敗（網路/金鑰/解析）
            return _rule_based_result(stock_code, data)   # 退回本地規則式結果
    return _rule_based_result(stock_code, data)           # 無金鑰：直接用本地規則式結果


def _analyze_with_openai(
    stock_code: str,                                      # 股票代號
    data: Dict[str, Any],                                 # 個股資料
    api_key: str,                                         # OpenAI 金鑰
    model: str,                                           # 模型名稱
) -> AnalysisResult:
    """呼叫 OpenAI 結構化輸出 API，將回應直接解析為 AnalysisResult。"""  # 函式說明
    from openai import OpenAI                              # 延遲匯入，避免未安裝時整體報錯
    client = OpenAI(api_key=api_key)                       # 建立 OpenAI 用戶端
    user_prompt = build_analysis_prompt(stock_code, data)  # 組裝使用者提示詞
    completion = client.beta.chat.completions.parse(       # 使用結構化輸出（傳入 Pydantic 綱要）
        model=model,                                       # 指定模型
        messages=[                                         # 對話訊息
            {"role": "system", "content": SYSTEM_PROMPT},  # 系統角色設定
            {"role": "user", "content": user_prompt},      # 使用者資料
        ],
        response_format=AnalysisResult,                    # 要求依此結構回傳（JSON 結構化輸出）
        temperature=0.3,                                   # 較低溫度以求穩定一致
    )
    parsed = completion.choices[0].message.parsed          # 取出已解析為模型的結果
    if parsed is None:                                     # 若模型拒答或解析失敗
        raise ValueError("OpenAI 未回傳可解析的結構化結果")  # 拋錯以觸發備援
    return parsed                                          # 回傳結構化結果


# =====================================================================
# 本地規則式備援：在無 AI 服務時產生同型別的結構化結果
# =====================================================================

def _flatten(data: Dict[str, Any]) -> Dict[str, Any]:
    """將分區資料攤平為單一字典，方便規則式評分讀取（後出現者覆蓋先出現者）。"""  # 函式說明
    flat: Dict[str, Any] = {}                             # 攤平後的字典
    for sec in ("financials", "valuation", "growth", "technical", "risk"):  # 逐一分區
        part = data.get(sec)                              # 取得分區
        if isinstance(part, dict):                        # 若為字典
            flat.update(part)                             # 併入
    for k, v in data.items():                             # 併入頂層非字典欄位
        if not isinstance(v, dict):                       # 僅取純量
            flat[k] = v                                   # 併入
    return flat                                           # 回傳攤平字典


def _g(flat: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """安全取數值欄位。"""                                  # 函式說明
    val = flat.get(key)                                   # 取值
    if val is None:                                       # 缺值
        return default                                    # 回傳預設
    try:                                                  # 嘗試轉數值
        return float(val)                                 # 回傳
    except (TypeError, ValueError):                       # 無法轉換
        return default                                    # 回傳預設


def _rule_based_result(stock_code: str, data: Dict[str, Any]) -> AnalysisResult:
    """以規則彙整五大面向訊號，產生與 AI 相同結構的分析結果（離線可用）。"""  # 函式說明
    flat = _flatten(data)                                 # 攤平資料
    score = 0.0                                           # 綜合評分起點
    reasons: List[str] = []                               # 關鍵理由
    available = 0                                         # 有效訊號計數（用於估算信心）

    # --- 財報基本面 ---
    roe = _g(flat, "roe")                                 # ROE
    if "roe" in flat:                                     # 若有 ROE
        available += 1                                    # 計數
        if roe >= 0.20:                                   # ROE 很高
            score += 2; reasons.append(f"獲利能力強，ROE 達 {format_percent(roe)}")  # 加分
        elif roe >= 0.10:                                 # ROE 不錯
            score += 1; reasons.append(f"ROE {format_percent(roe)} 表現穩健")  # 加分
        elif roe < 0.05:                                  # ROE 偏低
            score -= 1; reasons.append(f"ROE 僅 {format_percent(roe)}，獲利能力偏弱")  # 扣分
    if _g(flat, "net_margin") >= 0.15:                    # 淨利率高
        score += 1; reasons.append("淨利率優於一般水準，營運效率佳")  # 加分
    debt = _g(flat, "debt_ratio")                         # 負債比率
    if "debt_ratio" in flat:                              # 若有負債比
        available += 1                                    # 計數
        if debt > 0.7:                                    # 負債過高
            score -= 2; reasons.append(f"負債比率偏高（{format_percent(debt)}），財務風險較大")  # 扣分
        elif debt > 0.5:                                  # 負債稍高
            score -= 1                                    # 小幅扣分
    if 0 < _g(flat, "current_ratio") < 1:                 # 流動比 < 1
        score -= 1; reasons.append("流動比率低於 1，短期償債能力需留意")  # 扣分
    elif _g(flat, "current_ratio") >= 2:                  # 流動比充裕
        score += 0.5                                      # 小幅加分

    # --- 估值 ---
    upside = _g(flat, "upside")                           # 潛在漲幅
    if "upside" in flat:                                  # 若有估值
        available += 1                                    # 計數
        if upside >= 0.20:                                # 大幅低估
            score += 3; reasons.append(f"股價較合理價低估約 {format_percent(upside)}，安全邊際充足")  # 加分
        elif upside >= 0.10:                              # 低估
            score += 2; reasons.append(f"股價低於合理價約 {format_percent(upside)}")  # 加分
        elif upside > 0:                                  # 略低估
            score += 1                                    # 加分
        elif upside <= -0.20:                             # 大幅高估
            score -= 3; reasons.append(f"股價高於合理價約 {format_percent(abs(upside))}，下檔風險升高")  # 扣分
        elif upside < 0:                                  # 略高估
            score -= 1                                    # 扣分

    # --- 成長性 ---
    rev_yoy = _g(flat, "revenue_yoy")                     # 營收年增率
    if "revenue_yoy" in flat:                             # 若有成長資料
        available += 1                                    # 計數
        if rev_yoy >= 0.20:                               # 高成長
            score += 2; reasons.append(f"營收年增 {format_percent(rev_yoy)}，成長動能強勁")  # 加分
        elif rev_yoy >= 0.10:                             # 中成長
            score += 1; reasons.append(f"營收年增 {format_percent(rev_yoy)}，維持成長")  # 加分
        elif rev_yoy < 0:                                 # 衰退
            score -= 1; reasons.append("營收年減，成長動能轉弱")  # 扣分

    # --- 技術面 ---
    sharpe = _g(flat, "sharpe_ratio")                     # 夏普比率
    if "sharpe_ratio" in flat:                            # 若有技術資料
        available += 1                                    # 計數
        if sharpe >= 1:                                   # 風報比佳
            score += 1; reasons.append(f"夏普比率 {format_number(sharpe)}，風險報酬比佳")  # 加分
        elif sharpe < 0:                                  # 風報比差
            score -= 1                                    # 扣分
    if _g(flat, "annual_return") > 0:                     # 年化報酬為正
        score += 0.5                                      # 小幅加分
    rsi = _g(flat, "rsi")                                 # RSI
    if rsi >= 70:                                         # 超買
        score -= 1; reasons.append(f"RSI {format_number(rsi)} 進入超買區，短線追高風險")  # 扣分
    elif 0 < rsi <= 30:                                   # 超賣
        score += 1; reasons.append(f"RSI {format_number(rsi)} 進入超賣區，技術面具反彈機會")  # 加分

    # --- 風險 ---
    volatility = _g(flat, "volatility") or _g(flat, "annual_volatility")  # 波動度
    max_dd = _g(flat, "max_drawdown")                     # 最大回撤
    if volatility > 0.40:                                 # 波動偏大
        score -= 1; reasons.append("年化波動度偏高，價格波動劇烈")  # 扣分
    if max_dd < -0.40:                                    # 回撤深
        score -= 1; reasons.append(f"歷史最大回撤達 {format_percent(max_dd)}，下檔風險不小")  # 扣分

    # --- 綜合判定 ---
    score_int = int(max(-10, min(10, round(score))))      # 夾限並取整數
    recommendation = _score_to_recommendation(score_int)  # 由分數對應建議
    risk_level = _judge_risk(debt, volatility, max_dd)    # 判定風險等級
    confidence = max(0.0, min(95.0, 45 + available * 6 + abs(score_int) * 3))  # 估算信心

    # --- 目標價與潛在漲幅 ---
    target_price = flat.get("fair_value")                 # 目標價取合理價（可能為 None）
    target_price = float(target_price) if isinstance(target_price, (int, float)) else None  # 正規化
    upside_potential = round(upside * 100, 2) if "upside" in flat else None  # 潛在漲幅（百分比）

    if not reasons:                                       # 若無任何理由（資料極少）
        reasons.append("可用資料有限，建議審慎評估並參考更多資訊")  # 補上預設理由
        confidence = min(confidence, 40.0)                # 降低信心

    summary = (                                           # 組裝總結
        f"{stock_code} 綜合財報、估值、成長、技術面與風險評估後，"
        f"評分為 {score_int}（{recommendation}），風險等級為{risk_level}。"
        + (f"預估目標價約 {format_number(target_price)}。" if target_price else "")
        + "（本結論由系統規則式推論產出，僅供參考，投資請自行評估風險。）"
    )

    return AnalysisResult(                                 # 回傳結構化結果
        recommendation=recommendation,                    # 建議
        score=score_int,                                  # 評分
        confidence=round(confidence, 1),                  # 信心
        target_price=target_price,                        # 目標價
        upside_potential=upside_potential,                # 潛在漲幅
        risk_level=risk_level,                             # 風險等級
        key_reasons=reasons[:6],                           # 關鍵理由（最多 6 條）
        summary=summary,                                  # 總結
    )


def _score_to_recommendation(score: int) -> str:
    """將 -10~+10 的分數對應為五級操作建議。"""             # 函式說明
    if score >= 6:                                        # 強力買入
        return "強力買入"
    if score >= 2:                                        # 買入
        return "買入"
    if score >= -1:                                       # 持有
        return "持有"
    if score >= -5:                                       # 賣出
        return "賣出"
    return "強力賣出"                                      # 強力賣出


def _judge_risk(debt: float, volatility: float, max_dd: float) -> str:
    """依負債比、波動度與最大回撤綜合判定風險等級。"""        # 函式說明
    if debt > 0.6 or volatility > 0.40 or max_dd < -0.40:  # 任一偏高即為高風險
        return "高"
    if (debt and debt < 0.3) and (0 < volatility < 0.25):  # 結構穩健且波動低
        return "低"
    return "中"                                           # 其餘為中等風險


# =====================================================================
# 相容層：保留舊版 AIAnalyst（純文字分析），並提供結構化分析方法
# =====================================================================

class AIAnalyst:                                           # 定義 AI 投資分析師類別
    """整合量化結果並產生投資建議的分析師類別（相容舊版文字輸出，並支援結構化分析）。"""

    def __init__(self, api_key: str = None, model: str = None):  # 建構子，可覆寫金鑰與模型
        self.api_key = api_key or settings.openai_api_key  # 取得 OpenAI API 金鑰
        self.model = model or settings.openai_model        # 取得使用的模型名稱

    def build_prompt(                                      # 組裝（文字版）提示詞
        self,
        financials: Dict,                                  # 財報指標
        quant: Dict,                                       # 量化指標
        valuation: Dict,                                   # 估值結果
    ) -> str:
        """將各項分析資料整理為給 LLM 的中文提示詞。"""       # 方法說明
        lines = [                                          # 逐行組裝提示詞內容
            "你是一位專業的台股證券分析師，請根據以下資料，以繁體中文提供客觀的投資分析與建議。",  # 角色設定
            f"股票名稱：{financials.get('name', '未知')}（{financials.get('code', '')}）",  # 股票名稱與代號
            f"目前股價：{format_number(financials.get('price'))}",  # 目前股價
            f"本益比 PE：{format_number(financials.get('pe'))}",   # 本益比
            f"每股盈餘 EPS：{format_number(financials.get('eps'))}",  # 每股盈餘
            f"股東權益報酬率 ROE：{format_percent(financials.get('roe'))}",  # ROE
            f"年化報酬率：{format_percent(quant.get('annual_return'))}",  # 年化報酬率
            f"年化波動率：{format_percent(quant.get('annual_volatility'))}",  # 年化波動率
            f"夏普比率：{format_number(quant.get('sharpe_ratio'))}",  # 夏普比率
            f"最大回撤：{format_percent(quant.get('max_drawdown'))}",  # 最大回撤
            f"綜合合理價：{format_number(valuation.get('fair_value'))}",  # 估值合理價
            f"潛在漲幅：{format_percent(valuation.get('upside'))}",  # 潛在漲幅
            "請提供：1) 基本面評估 2) 風險提醒 3) 操作建議（買進/觀望/賣出），並說明理由。",  # 輸出要求
        ]
        return "\n".join(lines)                            # 以換行串接為完整提示詞

    def analyze(                                           # 產生（文字版）投資分析
        self,
        financials: Dict,                                  # 財報指標
        quant: Dict,                                       # 量化指標
        valuation: Dict,                                   # 估值結果
    ) -> str:
        """產生投資分析文字。優先使用 OpenAI；若不可用則使用本地規則式分析。"""  # 方法說明
        prompt = self.build_prompt(financials, quant, valuation)  # 先組裝提示詞
        if self.api_key:                                   # 若有設定 API 金鑰
            try:                                           # 嘗試呼叫 OpenAI
                return self._call_openai(prompt)           # 回傳 LLM 產生的分析
            except Exception:                              # 若呼叫失敗（網路、金鑰錯誤等）
                return ("[提示] AI 服務暫時不可用，改用本地規則分析。\n\n"  # 失敗時退回本地分析
                        + self._rule_based_analysis(financials, quant, valuation))
        return self._rule_based_analysis(financials, quant, valuation)  # 未設定金鑰時用本地分析

    def analyze_structured(                                # 產生結構化投資分析
        self,
        stock_code: str,                                  # 股票代號
        data: Dict[str, Any],                             # 個股各面向資料（財報/估值/成長/技術/風險）
    ) -> AnalysisResult:
        """以本分析師的金鑰與模型，產生結構化的 AnalysisResult。"""  # 方法說明
        return get_ai_analysis(stock_code, data, api_key=self.api_key, model=self.model)  # 委派核心函式

    def _call_openai(self, prompt: str) -> str:           # 實際呼叫 OpenAI 的私有方法
        """呼叫 OpenAI Chat Completions API 取得分析文字。"""  # 方法說明
        from openai import OpenAI                          # 延遲匯入 openai
        client = OpenAI(api_key=self.api_key)              # 建立 OpenAI 用戶端
        resp = client.chat.completions.create(             # 呼叫對話補全 API
            model=self.model,                              # 指定模型
            messages=[{"role": "user", "content": prompt}],  # 傳入提示詞
            temperature=0.4,                               # 控制回答的隨機性
        )
        return resp.choices[0].message.content             # 取出並回傳模型回覆內容

    def _rule_based_analysis(                              # 本地規則式（文字）分析
        self,
        financials: Dict,                                  # 財報指標
        quant: Dict,                                       # 量化指標
        valuation: Dict,                                   # 估值結果
    ) -> str:
        """以簡單規則產生分析文字，作為無 AI 服務時的備援。"""  # 方法說明
        roe = financials.get("roe") or 0                   # 取得 ROE
        sharpe = quant.get("sharpe_ratio") or 0            # 取得夏普比率
        upside = valuation.get("upside") or 0              # 取得潛在漲幅

        parts = []                                         # 收集分析段落
        if roe >= 0.15:                                    # ROE 高於 15%
            parts.append(f"基本面：ROE 達 {format_percent(roe)}，獲利能力佳。")  # 正面評語
        else:                                              # 否則
            parts.append(f"基本面：ROE 為 {format_percent(roe)}，獲利能力一般，需留意。")  # 中性評語

        if upside > 0.1:                                   # 潛在漲幅大於 10%
            parts.append(f"估值：目前股價較合理價低估約 {format_percent(upside)}，具吸引力。")  # 低估
        elif upside < -0.1:                                # 潛在漲幅小於 -10%
            parts.append(f"估值：目前股價較合理價高估約 {format_percent(abs(upside))}，偏貴。")  # 高估
        else:                                              # 介於中間
            parts.append("估值：目前股價接近合理價，評價中性。")  # 合理

        if sharpe >= 1:                                    # 夏普比率大於等於 1
            parts.append(f"風險：夏普比率 {format_number(sharpe)}，風險報酬比佳。")  # 風險可接受
        else:                                              # 否則
            parts.append(f"風險：夏普比率僅 {format_number(sharpe)}，報酬未充分補償波動風險。")  # 風險偏高

        if upside > 0.1 and roe >= 0.15:                   # 同時低估且基本面好
            advice = "操作建議：可考慮『買進』並分批布局。"     # 建議買進
        elif upside < -0.1:                                # 明顯高估
            advice = "操作建議：建議『賣出』或暫時觀望。"       # 建議賣出
        else:                                              # 其他情況
            advice = "操作建議：建議『觀望』，待更佳買點。"     # 建議觀望
        parts.append(advice)                               # 加入操作建議

        parts.append("（本分析為系統規則式產出，僅供參考，投資請自行評估風險。）")  # 免責聲明
        return "\n".join(parts)                            # 串接為完整分析文字


if __name__ == "__main__":                                # 直接執行此檔的簡易示範
    sample = {                                            # 範例：分區資料
        "financials": {"name": "台積電", "price": 600, "pe": 18, "eps": 33,
                       "roe": 0.25, "net_margin": 0.40, "debt_ratio": 0.28, "current_ratio": 2.2},
        "valuation": {"fair_value": 680, "upside": 0.13},  # 估值
        "growth": {"revenue_yoy": 0.22},                  # 成長
        "technical": {"annual_return": 0.18, "sharpe_ratio": 1.2, "rsi": 58, "max_drawdown": -0.18},  # 技術
        "risk": {"debt_ratio": 0.28, "volatility": 0.22},  # 風險
    }
    result = get_ai_analysis("2330", sample)              # 取得結構化分析（無金鑰則規則式）
    print("=== 結構化分析結果 ===")                        # 標題
    for k, v in result.model_dump().items():              # 逐欄印出
        print(f"{k}: {v}")                                # 印出欄位與值
