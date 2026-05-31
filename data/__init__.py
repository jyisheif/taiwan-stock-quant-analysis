# -*- coding: utf-8 -*-
"""data 套件：負責股市資料的擷取、清理與儲存。"""   # 套件說明，讓 data 成為可匯入的 Python 套件

from .fetcher import StockFetcher                     # 對外公開資料擷取類別
from .processor import DataProcessor                  # 對外公開資料處理類別
from .database import StockDatabase                   # 對外公開資料庫類別

__all__ = ["StockFetcher", "DataProcessor", "StockDatabase"]  # 定義 from data import * 時匯出的名稱
