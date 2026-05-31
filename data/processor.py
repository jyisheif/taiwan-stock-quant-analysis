# -*- coding: utf-8 -*-
"""
data/processor.py
資料處理模組：將擷取到的原始股價資料清理、轉換，並計算常用的衍生欄位
（例如日報酬率、移動平均線、累積報酬等），供後續量化分析使用。
"""

from __future__ import annotations                        # 啟用延遲型別評估

import pandas as pd                                       # 匯入 pandas 處理表格資料
import numpy as np                                        # 匯入 numpy 做數值運算


class DataProcessor:                                       # 定義資料處理類別
    """負責清理與加工股價資料的工具類別。"""               # 類別說明

    @staticmethod                                          # 靜態方法，不需建立實例即可呼叫
    def clean_price(df: pd.DataFrame) -> pd.DataFrame:     # 清理股價資料
        """
        清理原始股價資料：去除重複、處理缺失值、依日期排序。
        """
        if df is None or df.empty:                         # 若資料為空
            return pd.DataFrame()                          # 回傳空 DataFrame，避免後續錯誤
        out = df.copy()                                    # 複製一份避免修改到原始資料
        out.columns = [str(c).lower() for c in out.columns]  # 欄位名稱統一轉小寫
        if "date" in out.columns:                          # 若存在日期欄位
            out["date"] = pd.to_datetime(out["date"])      # 將日期欄位轉為 datetime 型別
            out = out.sort_values("date")                  # 依日期由舊到新排序
        out = out.drop_duplicates()                        # 去除完全重複的列
        out = out.dropna(subset=["close"])                 # 移除收盤價缺失的列（收盤價為必要欄位）
        out = out.reset_index(drop=True)                   # 重設索引並丟棄舊索引
        return out                                         # 回傳清理後的資料

    @staticmethod                                          # 靜態方法
    def add_returns(df: pd.DataFrame) -> pd.DataFrame:     # 計算報酬率欄位
        """
        新增日報酬率與累積報酬率欄位。
        """
        out = df.copy()                                    # 複製資料
        out["daily_return"] = out["close"].pct_change()    # 計算每日報酬率（今收/昨收 - 1）
        out["cum_return"] = (1 + out["daily_return"]).cumprod() - 1  # 計算累積報酬率
        return out                                         # 回傳新增欄位後的資料

    @staticmethod                                          # 靜態方法
    def add_moving_averages(                               # 計算移動平均線
        df: pd.DataFrame,
        windows: tuple = (5, 20, 60),                      # 預設計算 5、20、60 日均線
    ) -> pd.DataFrame:
        """
        為收盤價新增多條移動平均線（MA）。
        """
        out = df.copy()                                    # 複製資料
        for w in windows:                                  # 逐一處理每個視窗長度
            out[f"ma{w}"] = out["close"].rolling(w).mean() # 計算 w 日移動平均並存成新欄位
        return out                                         # 回傳結果

    @staticmethod                                          # 靜態方法
    def add_volatility(                                    # 計算滾動波動率
        df: pd.DataFrame,
        window: int = 20,                                  # 預設使用 20 日視窗
    ) -> pd.DataFrame:
        """
        計算指定視窗的滾動標準差（波動率），衡量價格波動程度。
        """
        out = df.copy()                                    # 複製資料
        if "daily_return" not in out.columns:              # 若尚未計算日報酬率
            out["daily_return"] = out["close"].pct_change()  # 先補上日報酬率欄位
        out[f"volatility_{window}"] = out["daily_return"].rolling(window).std()  # 計算滾動標準差
        return out                                         # 回傳結果

    @classmethod                                           # 類別方法，可串接多個處理步驟
    def enrich(cls, df: pd.DataFrame) -> pd.DataFrame:     # 一鍵加工：套用全部加工步驟
        """
        綜合處理：清理 -> 報酬率 -> 移動平均 -> 波動率，一次完成。
        """
        out = cls.clean_price(df)                           # 步驟一：清理資料
        if out.empty:                                       # 若清理後為空
            return out                                       # 直接回傳空表
        out = cls.add_returns(out)                          # 步驟二：加報酬率
        out = cls.add_moving_averages(out)                  # 步驟三：加移動平均
        out = cls.add_volatility(out)                       # 步驟四：加波動率
        return out                                           # 回傳完整加工後的資料


if __name__ == "__main__":                                  # 直接執行此檔的簡易示範
    from fetcher import StockFetcher                         # 匯入擷取器以取得合成資料
    raw = StockFetcher().generate_sample_price("2330")       # 產生合成股價
    enriched = DataProcessor.enrich(raw)                     # 套用完整加工
    print(enriched.tail(3))                                  # 印出加工後最後 3 筆資料
