import numpy as np
import pandas as pd
import vectorbt as vbt
from numba import njit

# Numba JIT ATR (Pine Script ta.atr RMA 완벽 재현)
@njit
def calc_atr_pine_nb(h, l, c, length):
    n = len(h)
    tr = np.full(n, np.nan)
    if n > 0: tr[0] = h[0] - l[0]
    for i in range(1, n):
        hl  = h[i] - l[i]
        hpc = abs(h[i] - c[i - 1])
        lpc = abs(l[i] - c[i - 1])
        tr[i] = max(hl, hpc, lpc)
    atr = np.full(n, np.nan)
    alpha = 1.0 / length
    sum_val = 0.0
    count = 0
    last = np.nan
    for i in range(n):
        if np.isnan(tr[i]): continue
        if np.isnan(last):
            sum_val += tr[i]
            count += 1
            if count == length:
                last = sum_val / length
                atr[i] = last
        else:
            last = alpha * tr[i] + (1.0 - alpha) * last
            atr[i] = last
    return atr

@njit
def compute_supertrend_nb(h, l, c, atr, multiplier):
    n = len(c)
    trend = np.full(n, np.nan)
    st_line = np.full(n, np.nan)
    
    for i in range(len(atr)):
        if np.isnan(atr[i]): continue
        hl2 = (h[i] + l[i]) / 2.0
        ub = hl2 + (multiplier * atr[i])
        lb = hl2 - (multiplier * atr[i])
        
        # SuperTrend Band logic
        if np.isnan(st_line[i-1]):
            trend[i] = 1 if c[i] > ub else -1
            st_line[i] = lb if trend[i] == 1 else ub
        else:
            prev_ub = st_line[i-1] if trend[i-1] == -1 else ub
            prev_lb = st_line[i-1] if trend[i-1] == 1 else lb
            
            curr_ub = ub if (ub < prev_ub or c[i-1] > prev_ub) else prev_ub
            curr_lb = lb if (lb > prev_lb or c[i-1] < prev_lb) else prev_lb
            
            prev_t = trend[i-1]
            if prev_t == 1 and c[i] < curr_lb:
                curr_t = -1
            elif prev_t == -1 and c[i] > curr_ub:
                curr_t = 1
            else:
                curr_t = prev_t
                
            trend[i] = curr_t
            st_line[i] = curr_lb if curr_t == 1 else curr_ub
            
    return trend, st_line

def run_simulation(df, params, split_ratio=0.70):
    """
    params:
      st_period, st_mult, ema_len, use_ema_filter,
      min_width_pct, use_min_volat,
      tr_ma_len, use_tr_exit,
      tp_mode, sl_mode, tp_fixed_pct, sl_fixed_pct, tp_atr_mult, sl_atr_mult,
      max_bars_hold, use_time_exit
    """
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    o = df['open'].values
    close_s = df['close']
    
    # 1. 지표 연산
    atr = calc_atr_pine_nb(h, l, c, params.get('st_period', 7))
    trend, st_line = compute_supertrend_nb(h, l, c, atr, params.get('st_mult', 3.0))
    
    # Macro EMA
    ema_len = params.get('ema_len', 200)
    macro_ema = close_s.ewm(span=ema_len, adjust=False).mean().values
    
    # TR MA
    tr_len = params.get('tr_ma_len', 100)
    tr_ma = close_s.ewm(span=tr_len, adjust=False).mean().values
    
    # 변동성 필터: (high - low)/close MA
    bar_volat = (df['high'] - df['low']) / df['close'] * 100
    volat_ma = bar_volat.rolling(20).mean().values
    min_volat = params.get('min_width_pct', 1.5)
    use_min_volat = params.get('use_min_volat', True)
    
    use_ema = params.get('use_ema_filter', True)
    use_tr = params.get('use_tr_exit', True)
    
    # 신호 생성
    n = len(df)
    long_raw = np.zeros(n, dtype=bool)
    short_raw = np.zeros(n, dtype=bool)
    
    for i in range(1, n):
        if np.isnan(trend[i]) or np.isnan(trend[i-1]): continue
        
        # Volatility pass
        v_ok = not use_min_volat or (volat_ma[i] >= min_volat)
        
        # SuperTrend Flip
        bull_flip = (trend[i] == 1) and (trend[i-1] == -1)
        bear_flip = (trend[i] == -1) and (trend[i-1] == 1)
        
        long_regime = not use_ema or (c[i] > macro_ema[i])
        short_regime = not use_ema or (c[i] < macro_ema[i])
        
        if bull_flip and long_regime and v_ok:
            long_raw[i] = True
        if bear_flip and short_regime and v_ok:
            short_raw[i] = True
            
    # Look-ahead Bias 방지: 다음 봉 시가 체결 (shift 1)
    long_sig = pd.Series(long_raw, index=df.index).shift(1).fillna(False).values
    short_sig = pd.Series(short_raw, index=df.index).shift(1).fillna(False).values
    
    # 2. 거래 시뮬레이션
    split_idx = int(n * split_ratio)
    
    def simulate_range(s_idx, e_idx):
        sub_c = c[s_idx:e_idx]
        sub_o = o[s_idx:e_idx]
        sub_h = h[s_idx:e_idx]
        sub_l = l[s_idx:e_idx]
        sub_atr = atr[s_idx:e_idx]
        sub_tr_ma = tr_ma[s_idx:e_idx]
        sub_ls = long_sig[s_idx:e_idx]
        sub_ss = short_sig[s_idx:e_idx]
        sub_idx = df.index[s_idx:e_idx]
        
        in_pos = 0 # 1, -1, 0
        entry_p = 0.0
        bars_held = 0
        
        ent_l = np.zeros(len(sub_c), dtype=bool)
        ext_l = np.zeros(len(sub_c), dtype=bool)
        ent_s = np.zeros(len(sub_c), dtype=bool)
        ext_s = np.zeros(len(sub_c), dtype=bool)
        
        trade_logs = []
        
        for i in range(len(sub_c)):
            ca = sub_atr[i] if not np.isnan(sub_atr[i]) else sub_c[i] * 0.015
            ch = sub_h[i]
            cl = sub_l[i]
            cc = sub_c[i]
            
            # 포지션 관리
            if in_pos == 1:
                bars_held += 1
                # TP / SL 계산
                fixed_tp = entry_p * (1.0 + params.get('tp_fixed_pct', 3.0) * 0.01)
                atr_tp   = entry_p + (params.get('tp_atr_mult', 3.5) * ca)
                tp_mode  = params.get('tp_mode', 'ATR')
                tp_p = fixed_tp if tp_mode == 'Fixed' else atr_tp if tp_mode == 'ATR' else max(fixed_tp, atr_tp) if tp_mode == 'Both' else 999999.0
                
                fixed_sl = entry_p * (1.0 - params.get('sl_fixed_pct', 2.0) * 0.01)
                atr_sl   = entry_p - (params.get('sl_atr_mult', 2.0) * ca)
                sl_mode  = params.get('sl_mode', 'ATR')
                sl_p = fixed_sl if sl_mode == 'Fixed' else atr_sl if sl_mode == 'ATR' else max(fixed_sl, atr_sl) if sl_mode == 'Both' else 0.0
                
                hit_tp = ch >= tp_p
                hit_sl = cl <= sl_p
                hit_tr = use_tr and (cc < sub_tr_ma[i])
                hit_time = params.get('use_time_exit', True) and (bars_held >= params.get('max_bars_hold', 72))
                hit_rev = sub_ss[i]
                
                if hit_tp or hit_sl or hit_tr or hit_time or hit_rev:
                    ext_l[i] = True
                    reason = "TP" if hit_tp else "SL" if hit_sl else "TR_MA" if hit_tr else "Time" if hit_time else "Reverse"
                    exit_price = tp_p if hit_tp else sl_p if hit_sl else sub_o[i]
                    pnl_pct = (exit_price / entry_p - 1.0) * 100 - 0.05
                    trade_logs.append({
                        'entry_time': str(entry_time), 'exit_time': str(sub_idx[i]),
                        'type': 'Long', 'entry_price': round(entry_p, 2), 'exit_price': round(exit_price, 2),
                        'pnl_pct': round(pnl_pct, 2), 'reason': reason
                    })
                    in_pos = 0
                    if hit_rev:
                        in_pos = -1
                        entry_p = sub_o[i]
                        entry_time = sub_idx[i]
                        bars_held = 0
                        ent_s[i] = True
                        
            elif in_pos == -1:
                bars_held += 1
                fixed_tp = entry_p * (1.0 - params.get('tp_fixed_pct', 3.0) * 0.01)
                atr_tp   = entry_p - (params.get('tp_atr_mult', 3.5) * ca)
                tp_mode  = params.get('tp_mode', 'ATR')
                tp_p = fixed_tp if tp_mode == 'Fixed' else atr_tp if tp_mode == 'ATR' else min(fixed_tp, atr_tp) if tp_mode == 'Both' else 0.0
                
                fixed_sl = entry_p * (1.0 + params.get('sl_fixed_pct', 2.0) * 0.01)
                atr_sl   = entry_p + (params.get('sl_atr_mult', 2.0) * ca)
                sl_mode  = params.get('sl_mode', 'ATR')
                sl_p = fixed_sl if sl_mode == 'Fixed' else atr_sl if sl_mode == 'ATR' else min(fixed_sl, atr_sl) if sl_mode == 'Both' else 999999.0
                
                hit_tp = cl <= tp_p
                hit_sl = ch >= sl_p
                hit_tr = use_tr and (cc > sub_tr_ma[i])
                hit_time = params.get('use_time_exit', True) and (bars_held >= params.get('max_bars_hold', 72))
                hit_rev = sub_ls[i]
                
                if hit_tp or hit_sl or hit_tr or hit_time or hit_rev:
                    ext_s[i] = True
                    reason = "TP" if hit_tp else "SL" if hit_sl else "TR_MA" if hit_tr else "Time" if hit_time else "Reverse"
                    exit_price = tp_p if hit_tp else sl_p if hit_sl else sub_o[i]
                    pnl_pct = (entry_p / exit_price - 1.0) * 100 - 0.05
                    trade_logs.append({
                        'entry_time': str(entry_time), 'exit_time': str(sub_idx[i]),
                        'type': 'Short', 'entry_price': round(entry_p, 2), 'exit_price': round(exit_price, 2),
                        'pnl_pct': round(pnl_pct, 2), 'reason': reason
                    })
                    in_pos = 0
                    if hit_rev:
                        in_pos = 1
                        entry_p = sub_o[i]
                        entry_time = sub_idx[i]
                        bars_held = 0
                        ent_l[i] = True
                        
            if in_pos == 0:
                if sub_ls[i]:
                    in_pos = 1
                    entry_p = sub_o[i]
                    entry_time = sub_idx[i]
                    bars_held = 0
                    ent_l[i] = True
                elif sub_ss[i]:
                    in_pos = -1
                    entry_p = sub_o[i]
                    entry_time = sub_idx[i]
                    bars_held = 0
                    ent_s[i] = True
                    
        # VectorBT 포트폴리오
        pf = vbt.Portfolio.from_signals(
            pd.Series(sub_c, index=sub_idx),
            entries=pd.Series(ent_l, index=sub_idx),
            exits=pd.Series(ext_l, index=sub_idx),
            short_entries=pd.Series(ent_s, index=sub_idx),
            short_exits=pd.Series(ext_s, index=sub_idx),
            fees=0.0005, slippage=0.0002, freq='1h'
        )
        
        t = pf.trades.count()
        sh = float(pf.sharpe_ratio()) if t > 0 else 0.0
        mdd = float(pf.max_drawdown()) * 100 if t > 0 else 100.0
        wr = float(pf.trades.win_rate()) * 100 if t > 0 else 0.0
        ret = float(pf.total_return()) * 100 if t > 0 else 0.0
        
        equity_series = pf.value()
        
        return {
            'trades_count': int(t),
            'sharpe': round(sh, 3),
            'mdd': round(mdd, 2),
            'win_rate': round(wr, 2),
            'return_pct': round(ret, 2),
            'equity': equity_series,
            'trades': trade_logs
        }
        
    is_res = simulate_range(0, split_idx)
    oos_res = simulate_range(split_idx, n)
    
    overfitting_ratio = oos_res['sharpe'] / is_res['sharpe'] if is_res['sharpe'] > 0 else 0.0
    
    return {
        'is': is_res,
        'oos': oos_res,
        'overfitting_ratio': round(overfitting_ratio, 3)
    }
