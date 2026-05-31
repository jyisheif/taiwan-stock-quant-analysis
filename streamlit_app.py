# -*- coding: utf-8 -*-
"""
streamlit_app.py
主程式（Web 介面）：以 Streamlit 打造美觀的台股財報量化分析儀表板。

頁面：
  1. 🏠 首頁         市場總覽（觀察名單漲跌、指標）+ AI 熱門推薦卡片
  2. 📊 個股分析     輸入代號後顯示 K 線圖、量化指標、三大財報、AI 投資建議卡片
  3. 🔍 自動選股器   多策略（價值/成長/品質/魔法公式/F-Score）篩選並以 AG Grid 顯示

技術：plotly 繪製互動圖表、streamlit-aggrid 顯示互動表格、AI 建議卡片以顏色區分多空。
執行：在專案根目錄執行 `streamlit run streamlit_app.py`
"""

import streamlit as st                                    # 匯入 Streamlit 建立網頁介面
import pandas as pd                                       # 匯入 pandas 處理表格資料

from config import settings                               # 匯入全域設定
from data.fetcher import StockFetcher                     # 匯入資料擷取類別
from data.processor import DataProcessor                  # 匯入資料處理類別
from data.database import StockDatabase                   # 匯入資料庫類別（報表快取）
from analysis.quant import QuantAnalyzer, FinancialMetrics  # 匯入量化分析與台股財務指標
from analysis.screener import StockScreener               # 匯入選股篩選類別
from analysis.valuation import ValuationModel             # 匯入估值模型類別
from ai.analyst import AIAnalyst, get_ai_analysis, AnalysisResult  # 匯入 AI 分析相關
from utils.helpers import format_percent, format_number   # 匯入格式化工具

try:                                                      # 嘗試匯入 plotly（互動圖表）
    import plotly.graph_objects as go                     # 匯入 plotly 圖形物件
    from plotly.subplots import make_subplots             # 匯入子圖工具（K 線 + 量）
    _PLOTLY = True                                        # 標記 plotly 可用
except ImportError:                                       # 若未安裝
    _PLOTLY = False                                       # 標記不可用

try:                                                      # 嘗試匯入 streamlit-aggrid（互動表格）
    from st_aggrid import AgGrid, GridOptionsBuilder      # 匯入 AG Grid 元件
    _AGGRID = True                                        # 標記可用
except ImportError:                                       # 若未安裝
    _AGGRID = False                                       # 標記不可用，改用內建表格


# =====================================================================
# 全域設定與樣式
# =====================================================================

st.set_page_config(                                       # 設定頁面基本資訊
    page_title="台股財報量化分析系統",                     # 瀏覽器分頁標題
    page_icon="📈",                                       # 分頁圖示
    layout="wide",                                        # 使用寬版版面
    initial_sidebar_state="expanded",                     # 預設展開側邊欄
)

# 自訂 CSS：美化指標卡片、AI 建議卡片與標題
st.markdown(
    """
    <style>
    .main > div { padding-top: 1rem; }                                  /* 縮減頁面上方留白 */
    .hero {                                                              /* 首頁標題橫幅 */
        background: linear-gradient(120deg, #1e3a8a 0%, #2563eb 100%);
        padding: 22px 28px; border-radius: 14px; color: white; margin-bottom: 18px;
    }
    .hero h1 { margin: 0; font-size: 28px; }                            /* 橫幅主標題 */
    .hero p  { margin: 6px 0 0 0; opacity: 0.9; }                       /* 橫幅副標題 */
    .ai-card {                                                          /* AI 建議卡片 */
        border-radius: 14px; padding: 18px 22px; margin: 6px 0 14px 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    }
    .ai-card h2 { margin: 0 0 4px 0; font-size: 26px; }                 /* 卡片建議文字 */
    .ai-badge {                                                         /* 卡片內小標籤 */
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 13px; margin-right: 8px; background: rgba(255,255,255,0.6);
    }
    .ai-reason { margin: 2px 0; font-size: 14px; color: #111111; }       /* 卡片理由列（黑色字） */
    .ai-badge  { color: #111111; }                                       /* 卡片標籤文字（黑色） */
    .stTabs [data-baseweb="tab"] p { font-size: 22px; font-weight: 600; }  /* 分頁標籤字體放大為 22 */
    </style>
    """,
    unsafe_allow_html=True,                                # 允許插入自訂 HTML/CSS
)

# 首頁觀察名單（台股代表性權值股）
TW_WATCHLIST = {                                          # 代號 -> 名稱
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電",
    "2303": "聯電", "2412": "中華電", "2882": "國泰金", "2603": "長榮",
}

# AI 建議的配色（綠=偏多、紅=偏空、黃=中性）
REC_STYLES = {                                            # 建議 -> (主色, 背景色, 圖示)
    "強力買入": ("#15803d", "#dcfce7", "🟢"),
    "買入":     ("#16a34a", "#ecfdf5", "🟢"),
    "持有":     ("#ca8a04", "#fef9c3", "🟡"),
    "賣出":     ("#dc2626", "#fee2e2", "🔴"),
    "強力賣出": ("#b91c1c", "#fde8e8", "🔴"),
}


# =====================================================================
# 共用元件
# =====================================================================

@st.cache_resource                                        # 快取資源，避免每次互動都重建物件
def get_components():                                     # 建立並回傳共用元件
    """建立並快取擷取器、處理器、AI 分析師與資料庫物件。"""  # 函式說明
    return StockFetcher(), DataProcessor(), AIAnalyst(), StockDatabase()  # 回傳四個共用物件


def show_table(df: pd.DataFrame, height: int = 320, key: str = None):  # 表格顯示元件
    """以 AG Grid 顯示可排序/篩選的互動表格；未安裝時退回 Streamlit 內建表格。"""  # 函式說明
    if df is None or df.empty:                            # 若無資料
        st.info("查無資料。")                              # 顯示提示
        return                                            # 結束
    if _AGGRID:                                           # 若 AG Grid 可用
        gb = GridOptionsBuilder.from_dataframe(df)        # 由 DataFrame 建立設定
        gb.configure_default_column(                      # 設定欄位預設行為
            resizable=True, filterable=True, sortable=True
        )
        AgGrid(                                            # 渲染 AG Grid 表格
            df,
            gridOptions=gb.build(),                       # 套用設定
            height=height,                                # 表格高度
            theme="streamlit",                            # 使用 Streamlit 主題
            fit_columns_on_grid_load=True,                # 載入時自動撐滿欄寬
            key=key,                                      # 唯一鍵（同頁多表需不同 key）
        )
    else:                                                 # 若無 AG Grid
        st.dataframe(df, use_container_width=True)        # 退回內建表格


def render_ai_card(result: AnalysisResult, subtitle: str = ""):  # AI 建議卡片元件
    """以醒目的彩色卡片顯示 AI 投資建議（依多空配色）。"""  # 函式說明
    color, bg, emoji = REC_STYLES.get(result.recommendation, ("#475569", "#f1f5f9", "⚪"))  # 取配色
    target = format_number(result.target_price) if result.target_price is not None else "—"  # 目標價
    upside = (f"{result.upside_potential:+.2f}%"          # 潛在漲幅（帶正負號）
              if result.upside_potential is not None else "—")
    reasons_html = "".join(                               # 將關鍵理由組成 HTML 列
        f"<div class='ai-reason'>• {r}</div>" for r in result.key_reasons
    )
    sub = f"<div style='color:#111111;margin-bottom:6px'>{subtitle}</div>" if subtitle else ""  # 副標（黑色字）
    st.markdown(                                          # 渲染卡片
        f"""
        <div class="ai-card" style="background:{bg}; border-left:10px solid {color};">
            {sub}
            <h2 style="color:{color};">{emoji} {result.recommendation}</h2>
            <div style="margin:8px 0;">
                <span class="ai-badge">評分 <b>{result.score:+d}</b> / 10</span>
                <span class="ai-badge">信心 <b>{result.confidence:.0f}%</b></span>
                <span class="ai-badge">風險 <b>{result.risk_level}</b></span>
                <span class="ai-badge">目標價 <b>{target}</b></span>
                <span class="ai-badge">潛在漲幅 <b>{upside}</b></span>
            </div>
            {reasons_html}
        </div>
        """,
        unsafe_allow_html=True,                            # 允許自訂 HTML
    )


# =====================================================================
# 資料計算（含快取）
# =====================================================================

def _load_statements_cached(fetcher, db, code, quarterly, ignore_cache):  # 取得三大報表（含快取）
    """優先讀 SQLite 快取，無或要求忽略時才重新擷取並寫回。回傳 (報表, 是否來自快取)。"""  # 函式說明
    if not ignore_cache and db.has_statements(code, quarterly):  # 若快取存在且不忽略
        return db.load_statements(code, quarterly), True   # 回傳快取
    statements = fetcher.get_financial_statements(code, quarterly=quarterly)  # 重新擷取
    db.save_statements(code, statements, quarterly)        # 寫回快取
    return statements, False                               # 回傳新資料


@st.cache_data(ttl=600, show_spinner=False)               # 快取市場總覽 10 分鐘
def compute_market_overview(_fetcher, codes: tuple) -> pd.DataFrame:  # 計算市場總覽
    """為觀察名單計算最新收盤、日漲跌幅與基本指標。"""      # 函式說明
    rows = []                                             # 收集每檔資料
    for code in codes:                                    # 逐一處理
        price = _fetcher.fetch_price_history(code, "3mo")  # 取近三月股價
        fin = _fetcher.fetch_financials(code)             # 取基本面
        if price is not None and len(price) >= 2:         # 若有足夠資料
            last = float(price["close"].iloc[-1])         # 最新收盤
            prev = float(price["close"].iloc[-2])         # 前一日收盤
            change = (last / prev - 1) * 100 if prev else 0.0  # 日漲跌幅
        else:                                             # 否則
            last = fin.get("price") or 0                  # 退用基本面股價
            change = 0.0                                   # 漲跌幅 0
        rows.append({                                     # 收集一列
            "代號": code,                                  # 代號
            "名稱": TW_WATCHLIST.get(code, code),          # 名稱
            "收盤": round(last, 2),                        # 收盤
            "漲跌幅(%)": round(change, 2),                 # 漲跌幅
            "本益比": fin.get("pe"),                        # 本益比
            "ROE(%)": round((fin.get("roe") or 0) * 100, 2),  # ROE 百分比
        })
    return pd.DataFrame(rows)                             # 回傳總覽表


@st.cache_data(ttl=600, show_spinner=False)               # 快取熱門推薦 10 分鐘
def compute_recommendations(_fetcher, _processor, codes: tuple) -> list:  # 計算 AI 熱門推薦
    """對觀察名單以本地規則式 AI 評分（離線、不耗費 token），回傳依分數排序的清單。"""  # 函式說明
    results = []                                          # 收集 (代號, 名稱, 結果)
    for code in codes:                                    # 逐一處理
        fin = _fetcher.fetch_financials(code)             # 基本面
        price = _processor.enrich(_fetcher.fetch_price_history(code, "1y"))  # 加工後股價
        quant = QuantAnalyzer(price).summary()            # 量化指標
        val = ValuationModel.evaluate(fin)                # 估值
        data = {                                          # 組裝五大面向資料
            "financials": fin, "valuation": val, "technical": quant,
            "growth": {"revenue_yoy": fin.get("revenue_yoy")},
            "risk": {"debt_ratio": fin.get("debt_ratio"),
                     "volatility": quant.get("annual_volatility"),
                     "max_drawdown": quant.get("max_drawdown")},
        }
        res = get_ai_analysis(code, data, api_key="")     # 首頁固定用規則式（離線）以免大量呼叫 API
        results.append((code, fin.get("name", code), res))  # 收集
    results.sort(key=lambda x: x[2].score, reverse=True)  # 依評分由高到低排序
    return results                                        # 回傳排序後清單


def price_chart(df: pd.DataFrame):                        # 繪製 K 線 + 均線 + 成交量圖
    """以 plotly 繪製含均線與成交量的互動 K 線圖。"""        # 函式說明
    fig = make_subplots(                                  # 建立上下兩個子圖
        rows=2, cols=1, shared_xaxes=True,                # 共用 X 軸
        row_heights=[0.74, 0.26], vertical_spacing=0.03,  # 上圖較高、下圖較矮
    )
    fig.add_trace(                                        # 上圖：K 線
        go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="K 線",
            increasing_line_color="#dc2626", decreasing_line_color="#16a34a",  # 台股慣例：紅漲綠跌
        ),
        row=1, col=1,
    )
    for ma, color in [("ma5", "#f59e0b"), ("ma20", "#2563eb"), ("ma60", "#7c3aed")]:  # 疊加均線
        if ma in df.columns:                              # 若該均線存在
            fig.add_trace(
                go.Scatter(x=df["date"], y=df[ma], name=ma.upper(),
                           line=dict(width=1.2, color=color)),
                row=1, col=1,
            )
    if "volume" in df.columns:                            # 下圖：成交量
        fig.add_trace(
            go.Bar(x=df["date"], y=df["volume"], name="成交量", marker_color="#94a3b8"),
            row=2, col=1,
        )
    fig.update_layout(                                    # 版面設定
        height=520, xaxis_rangeslider_visible=False,      # 隱藏下方範圍滑桿
        legend=dict(orientation="h", y=1.02, x=0),        # 圖例水平置頂
        margin=dict(l=10, r=10, t=30, b=10),              # 邊距
    )
    return fig                                            # 回傳圖形


# =====================================================================
# 頁面一：首頁（市場總覽 + 熱門推薦）
# =====================================================================

def render_home(fetcher, processor):                      # 渲染首頁
    """首頁：市場總覽與 AI 熱門推薦。"""                     # 函式說明
    st.markdown(                                          # 標題橫幅
        """
        <div class="hero">
            <h1>📈 台股財報選股量化分析系統</h1>
            <p>整合財報分析、量化指標、估值模型與 AI 投資建議，一站式掌握台股機會。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    codes = tuple(TW_WATCHLIST.keys())                    # 觀察名單代號
    with st.spinner("載入市場資料中..."):                  # 載入動畫
        overview = compute_market_overview(fetcher, codes)  # 市場總覽
        recs = compute_recommendations(fetcher, processor, codes)  # 熱門推薦

    # --- 市場總覽指標列 ---
    st.subheader("📊 市場總覽")                            # 區塊標題
    up = int((overview["漲跌幅(%)"] > 0).sum())            # 上漲家數
    down = int((overview["漲跌幅(%)"] < 0).sum())          # 下跌家數
    avg_chg = overview["漲跌幅(%)"].mean()                 # 平均漲跌幅
    k1, k2, k3, k4 = st.columns(4)                         # 四個摘要卡片
    k1.metric("觀察檔數", f"{len(overview)} 檔")           # 觀察檔數
    k2.metric("上漲 / 下跌", f"{up} / {down}")             # 漲跌家數
    k3.metric("平均漲跌幅", f"{avg_chg:+.2f}%")            # 平均漲跌幅
    buy_cnt = sum(1 for _, _, r in recs if r.score >= 2)   # AI 偏多檔數
    k4.metric("AI 偏多訊號", f"{buy_cnt} 檔")              # AI 偏多檔數

    c_left, c_right = st.columns([3, 2])                   # 左右兩欄：表格 + 圖
    with c_left:                                          # 左欄：觀察名單表格
        st.markdown("**觀察名單**")                        # 小標題
        show_table(overview, height=320, key="overview")  # 以 AG Grid 顯示
    with c_right:                                         # 右欄：漲跌幅長條圖
        st.markdown("**今日漲跌幅**")                      # 小標題
        if _PLOTLY:                                       # 若 plotly 可用
            colors = ["#dc2626" if v >= 0 else "#16a34a" for v in overview["漲跌幅(%)"]]  # 紅漲綠跌
            fig = go.Figure(go.Bar(                       # 長條圖
                x=overview["名稱"], y=overview["漲跌幅(%)"], marker_color=colors
            ))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),  # 版面
                              yaxis_title="漲跌幅(%)")
            st.plotly_chart(fig, use_container_width=True)  # 顯示圖
        else:                                             # 無 plotly 時
            st.bar_chart(overview.set_index("名稱")["漲跌幅(%)"])  # 內建長條圖

    # --- AI 熱門推薦 ---
    st.subheader("🔥 AI 熱門推薦")                         # 區塊標題
    st.caption("依本地規則式 AI 綜合評分排序（首頁離線計算，不耗用 API 額度）。")  # 說明
    top = recs[:3]                                        # 取分數最高三檔
    cols = st.columns(3)                                  # 三欄並排
    for col, (code, name, res) in zip(cols, top):         # 逐一渲染卡片
        with col:                                         # 進入該欄
            render_ai_card(res, subtitle=f"{name}（{code}）")  # 顯示 AI 卡片


# =====================================================================
# 頁面二：個股分析
# =====================================================================

def _render_statement_block(title, df, key_item, grid_key):  # 渲染單一財報 + 成長圖
    """顯示一份財報的表格（AG Grid），並針對關鍵科目繪製金額與成長率組合圖。"""  # 函式說明
    st.markdown(f"#### {title}")                          # 報表名稱
    if df is None or df.empty:                            # 若無資料
        st.warning(f"查無{title}資料。")                   # 提醒
        return                                            # 結束
    show_table(df.reset_index().rename(columns={"index": "科目"}), height=260, key=grid_key)  # 表格

    series = df.loc[key_item] if key_item in df.index else None  # 取關鍵科目
    if series is None:                                    # 若無此科目
        return                                            # 不繪圖
    periods = list(series.index)[::-1]                    # 期間由舊到新
    values = [series[p] for p in periods]                 # 對應數值
    growth = [None] + [                                   # 計算期間成長率（%）
        ((values[i] - values[i - 1]) / abs(values[i - 1]) * 100) if values[i - 1] else None
        for i in range(1, len(values))
    ]
    if _PLOTLY:                                           # 若 plotly 可用
        fig = go.Figure()                                 # 建立圖
        fig.add_trace(go.Bar(x=periods, y=values, name=key_item, marker_color="#3b82f6"))  # 金額長條
        fig.add_trace(go.Scatter(x=periods, y=growth, name="成長率(%)", yaxis="y2",  # 成長率折線
                                 mode="lines+markers", line=dict(color="#f59e0b")))
        fig.update_layout(                               # 雙 Y 軸版面
            yaxis=dict(title="金額"), yaxis2=dict(title="成長率(%)", overlaying="y", side="right"),
            legend=dict(orientation="h"), height=320, margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)    # 顯示圖


def render_single_stock(fetcher, processor, analyst, db, source):  # 渲染個股分析頁
    """個股分析頁：以分頁呈現量化分析、財務報表與 AI 投資建議卡片。"""  # 函式說明
    st.header("📊 個股分析")                               # 頁面標題
    col_code, col_period, col_freq = st.columns([2, 1, 1])  # 輸入元件
    code = col_code.text_input("股票代號", "2330")         # 股票代號
    period = col_period.selectbox("資料區間", ["6mo", "1y", "2y", "5y"], index=1)  # 區間
    freq_label = col_freq.selectbox("財報週期", ["年報", "季報"], index=0)  # 財報週期
    quarterly = freq_label == "季報"                      # 轉布林
    ignore_cache = st.checkbox("忽略本地快取，重新擷取財報", value=False)  # 強制重抓

    if not st.button("開始分析", type="primary"):         # 未按按鈕
        st.info("輸入股票代號後按「開始分析」。")            # 提示
        return                                            # 結束

    with st.spinner("資料擷取與分析中..."):                # 載入動畫
        raw = fetcher.fetch_price_history(code, period, source=source)  # 股價
        df = processor.enrich(raw)                         # 加工
        financials = fetcher.fetch_financials(code)        # 基本面
        quant = QuantAnalyzer(df).summary()                # 量化指標
        valuation = ValuationModel.evaluate(financials)    # 估值
        statements, from_cache = _load_statements_cached(  # 三大報表（含快取）
            fetcher, db, code, quarterly, ignore_cache
        )
        metrics = FinancialMetrics(                        # 財務指標計算器
            statements, freq="quarterly" if quarterly else "annual", market=financials
        )
        summary = metrics.summary()                        # 財務指標摘要

    st.subheader(f"{financials.get('name', code)}（{code}）")  # 公司名稱與代號

    tab_quant, tab_stmt, tab_ai = st.tabs(["📈 量化分析", "📑 財務報表", "🤖 AI 建議"])  # 三個分頁

    # ---------------- 分頁一：量化分析 ----------------
    with tab_quant:                                       # 量化分析
        c1, c2, c3, c4 = st.columns(4)                     # 四個指標卡片
        c1.metric("年化報酬率", format_percent(quant["annual_return"]))  # 年化報酬
        c2.metric("年化波動率", format_percent(quant["annual_volatility"]))  # 年化波動
        c3.metric("夏普比率", format_number(quant["sharpe_ratio"]))  # 夏普比率
        c4.metric("最大回撤", format_percent(quant["max_drawdown"]))  # 最大回撤

        st.markdown("#### 股價走勢（K 線）")                # 圖表標題
        if _PLOTLY and not df.empty:                       # 若可用且有資料
            st.plotly_chart(price_chart(df), use_container_width=True)  # K 線圖
        elif not df.empty:                                 # 退回內建圖
            st.line_chart(df.set_index("date")["close"])

        st.markdown("#### 估值分析")                        # 估值標題
        v1, v2, v3 = st.columns(3)                         # 三欄
        v1.metric("目前股價", format_number(valuation["current_price"]))  # 股價
        v2.metric("綜合合理價", format_number(valuation["fair_value"]))  # 合理價
        v3.metric("潛在漲幅", format_percent(valuation["upside"]))  # 潛在漲幅

    # ---------------- 分頁二：財務報表 ----------------
    with tab_stmt:                                        # 財務報表
        note = "（本地快取）" if from_cache else "（即時擷取，已寫入快取）"  # 快取狀態
        st.caption(f"目前顯示：{freq_label}{note}，最多近 {settings.statement_max_periods} 期。")  # 說明

        st.markdown("#### 關鍵財務指標（最新一期）")          # 區塊標題
        m = st.columns(4)                                  # 四欄
        m[0].metric("毛利率", format_percent(summary["毛利率"]))      # 毛利率
        m[1].metric("營業利益率", format_percent(summary["營業利益率"]))  # 營業利益率
        m[2].metric("淨利率", format_percent(summary["淨利率"]))      # 淨利率
        m[3].metric("ROE", format_percent(summary["ROE"]))           # ROE
        n = st.columns(4)                                  # 第二排
        n[0].metric("ROA", format_percent(summary["ROA"]))          # ROA
        n[1].metric("EPS", format_number(summary["EPS"]))            # EPS
        n[2].metric("PER", format_number(summary["PER"]))            # 本益比
        n[3].metric("PBR", format_number(summary["PBR"]))            # 股價淨值比

        st.markdown("#### 財務比率趨勢")                    # 區塊標題
        ratios = metrics.ratio_trends()                    # 逐期比率
        pct_cols = ["毛利率", "營業利益率", "淨利率", "ROE", "ROA", "負債比率"]  # 百分比欄位
        ratios_pct = ratios[[c for c in pct_cols if c in ratios.columns]].dropna(how="all")  # 取欄位
        if not ratios_pct.empty and _PLOTLY:               # 若有資料且 plotly 可用
            fig = go.Figure()                              # 建圖
            for col in ratios_pct.columns:                 # 逐比率畫線
                fig.add_trace(go.Scatter(x=list(ratios_pct.index), y=(ratios_pct[col] * 100).round(2),
                                         name=col, mode="lines+markers"))
            fig.update_layout(yaxis=dict(title="比率(%)"), legend=dict(orientation="h"),
                              height=360, margin=dict(l=10, r=10, t=10, b=10))  # 版面
            st.plotly_chart(fig, use_container_width=True)  # 顯示
        elif not ratios_pct.empty:                         # 退回內建圖
            st.line_chart(ratios_pct * 100)

        st.markdown("---")                                # 分隔線
        _render_statement_block("損益表", statements["損益表"], "營業收入", "g_income")  # 損益表
        _render_statement_block("資產負債表", statements["資產負債表"], "資產總額", "g_balance")  # 資產負債表
        _render_statement_block("現金流量表", statements["現金流量表"], "營業活動現金流", "g_cash")  # 現金流量表

    # ---------------- 分頁三：AI 投資建議 ----------------
    with tab_ai:                                          # AI 建議
        ai_data = {                                       # 組裝五大面向資料
            "financials": {**financials, **{k: summary.get(k) for k in
                           ["毛利率", "淨利率", "ROE", "ROA", "EPS"]}},
            "valuation": valuation,
            "growth": {"revenue_yoy": summary.get("營收年增率"), "net_yoy": summary.get("淨利年增率")},
            "technical": quant,
            "risk": {"debt_ratio": summary.get("負債比率"),
                     "volatility": quant.get("annual_volatility"),
                     "max_drawdown": quant.get("max_drawdown")},
        }
        result = analyst.analyze_structured(code, ai_data)  # 取得結構化 AI 分析
        render_ai_card(result, subtitle=f"{financials.get('name', code)}（{code}） AI 投資建議")  # 卡片
        st.markdown(                                       # 顯示總結（黑色字）
            f"<div style='background:#f1f5f9;border-radius:10px;padding:14px 16px;"
            f"color:#111111;font-size:15px;'>{result.summary}</div>",
            unsafe_allow_html=True,
        )
        with st.expander("查看文字版分析"):                 # 收合：文字分析
            st.write(analyst.analyze(financials, quant, valuation))  # 文字版


# =====================================================================
# 頁面三：自動選股器
# =====================================================================

def _build_metrics_pool(fetcher, db, codes):              # 以 FinancialMetrics 建立選股紀錄
    """對每檔股票取報表（優先快取）並算完整指標，轉成選股器紀錄。"""  # 函式說明
    pool = []                                             # 收集紀錄
    for code in codes:                                    # 逐一處理
        market = fetcher.fetch_financials(code)           # 市場/基本面
        stmts, _ = _load_statements_cached(fetcher, db, code, quarterly=False, ignore_cache=False)  # 報表
        metrics = FinancialMetrics(stmts, freq="annual", market=market)  # 指標計算器
        record = metrics.to_record(code, name=market.get("name", code))  # 轉紀錄
        if record.get("dividend_yield") is None:          # 補殖利率
            record["dividend_yield"] = market.get("dividend_yield")
        pool.append(record)                               # 收集
    return pool                                           # 回傳


def render_screener(fetcher, db):                         # 渲染自動選股頁
    """自動選股頁：多策略篩選並以 AG Grid 顯示結果。"""      # 函式說明
    st.header("🔍 自動選股器")                             # 頁面標題
    codes_text = st.text_area(                             # 多檔代號輸入
        "輸入欲篩選的股票代號（以逗號分隔）",
        "2330, 2317, 2454, 2308, 2303, 2412, 2882, 2603, 1101, 2891",
    )
    use_metrics = st.checkbox("使用完整財報指標（含毛利率/流動比率/FCF，計算較慢）", value=False)  # 完整指標

    strat_map = {"多條件加權（預設）": None}               # 策略標籤對名稱
    for name, desc in StockScreener.available_strategies().items():  # 加入已註冊策略
        strat_map[f"{name}｜{desc}"] = name               # 標籤
    strat_label = st.selectbox("選股策略", list(strat_map.keys()), index=0)  # 策略選單
    strategy = strat_map[strat_label]                      # 對應名稱
    apply_filter = st.checkbox("套用策略前先以下方條件過濾", value=(strategy is None))  # 是否先過濾

    col1, col2 = st.columns(2)                             # 基本條件滑桿
    min_roe = col1.slider("最低 ROE", 0.0, 0.3, settings.min_roe, 0.01)  # ROE
    max_pe = col2.slider("最高本益比", 5.0, 50.0, settings.max_pe, 1.0)  # 本益比
    min_eps = col1.slider("最低 EPS", 0.0, 10.0, settings.min_eps, 0.5)  # EPS
    max_debt = col2.slider("最高負債比", 0.0, 1.0, settings.max_debt_ratio, 0.05)  # 負債比

    min_gm = min_cr = min_fcf = None                      # 進階門檻預設 None
    if use_metrics:                                       # 啟用完整指標時
        st.markdown("**進階條件**")                        # 標題
        a1, a2, a3 = st.columns(3)                         # 三欄
        min_gm = a1.slider("最低毛利率", 0.0, 0.8, 0.0, 0.05)   # 毛利率
        min_cr = a2.slider("最低流動比率", 0.0, 5.0, 0.0, 0.1)  # 流動比率
        min_fcf = a3.slider("最低 FCF 殖利率", 0.0, 0.15, 0.0, 0.01)  # FCF 殖利率

    if st.button("執行選股", type="primary"):             # 選股按鈕
        codes = [c.strip() for c in codes_text.split(",") if c.strip()]  # 解析代號
        with st.spinner("擷取財報並篩選中..."):            # 載入動畫
            pool = (_build_metrics_pool(fetcher, db, codes) if use_metrics  # 完整指標
                    else [fetcher.fetch_financials(c) for c in codes])      # 或快速指標
            screener = StockScreener(                      # 建立篩選器
                min_roe, max_pe, min_eps, max_debt,
                min_gross_margin=min_gm, min_current_ratio=min_cr, min_fcf_yield=min_fcf,
            )
            result = screener.screen(pool, strategy=strategy, apply_filter=apply_filter)  # 執行

        if result.empty:                                   # 若無結果
            st.warning("沒有符合條件的股票，請放寬篩選條件。")  # 提醒
        else:                                              # 有結果
            st.success(f"共有 {len(result)} 檔股票通過篩選！（策略：{strat_label}）")  # 訊息
            base = ["code", "name", "roe", "pe", "eps"]    # 基本欄位
            adv = ["gross_margin", "current_ratio", "fcf_yield", "revenue_yoy"]  # 進階欄位
            extra = ["fscore", "earnings_yield", "roc", "score"]  # 策略特有欄位
            cols = base + (adv if use_metrics else []) + extra  # 組合
            cols = [c for c in cols if c in result.columns]  # 過濾不存在欄位
            show_table(result[cols], height=380, key="screen_result")  # AG Grid 顯示
            st.download_button(                            # 提供 CSV 下載
                "下載結果 CSV",
                result[cols].to_csv(index=False).encode("utf-8-sig"),
                file_name="screen_result.csv", mime="text/csv",
            )


# =====================================================================
# 主程式
# =====================================================================

def main():                                               # 主函式：組裝整個應用程式
    """應用程式進入點：建立側邊欄並切換不同頁面。"""          # 函式說明
    fetcher, processor, analyst, db = get_components()     # 取得共用元件

    st.sidebar.title("📈 台股量化分析")                    # 側邊欄標題
    page = st.sidebar.radio("功能選單", ["🏠 首頁", "📊 個股分析", "🔍 自動選股器"])  # 頁面切換
    st.sidebar.markdown("---")                             # 分隔線

    source_label = st.sidebar.radio("股價資料來源", ["Yahoo Finance", "twstock（台股）"], index=0)  # 來源
    source = "twstock" if source_label.startswith("twstock") else "yfinance"  # 內部代碼
    st.sidebar.markdown("---")                             # 分隔線

    api_key_input = st.sidebar.text_input(                 # OpenAI 金鑰輸入
        "OpenAI API Key（選填）", type="password", value="",
        help="輸入後個股 AI 建議將改用 OpenAI 模型；留空則使用本地規則式分析。",
    )
    analyst.api_key = api_key_input.strip() or settings.openai_api_key  # 以 UI 金鑰覆寫
    if analyst.api_key:                                    # 若有金鑰
        st.sidebar.success("已啟用 OpenAI AI 分析")          # 啟用狀態
    else:                                                  # 否則
        st.sidebar.caption("AI 分析使用本地規則式（未設定金鑰）")  # 本地模式

    st.sidebar.markdown("---")                             # 分隔線
    st.sidebar.info("無網路或來源失敗時，將自動改用模擬資料以維持系統運作。")  # 說明

    if page.endswith("首頁"):                              # 首頁
        render_home(fetcher, processor)                    # 渲染首頁
    elif page.endswith("個股分析"):                        # 個股分析
        render_single_stock(fetcher, processor, analyst, db, source)  # 渲染個股分析
    else:                                                  # 自動選股器
        render_screener(fetcher, db)                       # 渲染選股器


if __name__ == "__main__":                                # 當此檔被直接執行時
    main()                                                # 執行主函式啟動應用程式
