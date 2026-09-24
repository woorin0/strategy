import ccxt
import pandas as pd
import numpy as np
import os
import hashlib
import time

CACHE_DIR = "cache"

def get_timeframe_ms(timeframe):
    unit = timeframe[-1]
    num = int(timeframe[:-1])
    if unit == 'm': return num * 60 * 1000
    if unit == 'h': return num * 60 * 60 * 1000
    if unit == 'd': return num * 24 * 60 * 60 * 1000
    return 60 * 60 * 1000

def get_cached_data(symbol="BTC/USDT", timeframe="1h", start_date="2023-06-01", padding_candles=250):
    """지표 Warm-up 패딩 및 Parquet 캐싱을 지원하는 데이터 로더"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        
    clean_sym = symbol.replace("/", "_")
    key = f"binance_{clean_sym}_{timeframe}_{start_date}_p{padding_candles}"
    hash_key = hashlib.md5(key.encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"data_{hash_key}.parquet")
    
    # 1. 고유 해시 캐시 확인
    if os.path.exists(cache_path):
        return pd.read_parquet(cache_path)
        
    # 2. 로컬에 기존 수집된 parquet 파일이 있는지 확인 (Fallback)
    local_map = {
        ("BTC/USDT", "1h"): "data_btc_1h.parquet",
        ("BTC/USDT", "15m"): "data_btc_15m.parquet",
        ("ETH/USDT", "1h"): "data_eth_1h.parquet",
        ("SOL/USDT", "1h"): "data_sol_1h.parquet"
    }
    
    if (symbol, timeframe) in local_map and os.path.exists(local_map[(symbol, timeframe)]):
        df = pd.read_parquet(local_map[(symbol, timeframe)])
        df.to_parquet(cache_path)
        return df

    # 3. 없으면 Binance CCXT를 통해 자동 수집
    exchange = ccxt.binance({'enableRateLimit': True, 'timeout': 30000})
    tf_ms = get_timeframe_ms(timeframe)
    base_since = int(pd.to_datetime(start_date).timestamp() * 1000)
    since = base_since - (padding_candles * tf_ms)
    
    all_ohlcv = []
    limit = 1000
    now = exchange.milliseconds()
    
    while since < now:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
            if not ohlcv: break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + tf_ms
            if len(ohlcv) < limit: break
            time.sleep(exchange.rateLimit / 1000)
        except Exception:
            break
            
    if not all_ohlcv:
        raise RuntimeError(f"데이터 수집 실패: {symbol} ({timeframe})")
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated(keep='first')]
    df.sort_index(inplace=True)
    df.to_parquet(cache_path)
    return df
