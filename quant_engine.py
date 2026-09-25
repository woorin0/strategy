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

# [Squeeze Momentum (LazyBear) Numba JIT 계산기]
@njit
def compute_squeeze_momentum_nb(h, l, c, length=20, mult_bb=2.0, mult_kc=1.5):
    n = len(c)
    squeeze_on = np.zeros(n, dtype=np.bool_)
    squeeze_off = np.zeros(n, dtype=np.bool_)
    momentum = np.zeros(n, dtype=np.float64)
    
    for i in range(length, n):
        # BB 계산
        c_win = c[i-length+1:i+1]
        sma_bb = np.mean(c_win)
        std_bb = np.std(c_win)
        bb_up = sma_bb + mult_bb * std_bb
        bb_dn = sma_bb - mult_bb * std_bb
        
        # KC 계산
        h_win = h[i-length+1:i+1]
        l_win = l[i-length+1:i+1]
        tr_sum = 0.0
        for j in range(i-length+1, i+1):
            tr_val = max(h[j] - l[j], abs(h[j] - c[j-1]), abs(l[j] - c[j-1]))
            tr_sum += tr_val
        atr_kc = tr_sum / length
        kc_up = sma_bb + mult_kc * atr_kc
        kc_dn = sma_bb - mult_kc * atr_kc
        
        # Squeeze On / Off
        sqz_on = (bb_dn > kc_dn) and (bb_up < kc_up)
        squeeze_on[i] = sqz_on
        squeeze_off[i] = not sqz_on
        
        # Momentum 계산: Close - Donchian/SMA Average
        highest_h = np.max(h_win)
        lowest_l = np.min(l_win)
        avg_price = ((highest_h + lowest_l) / 2.0 + sma_bb) / 2.0
        momentum[i] = c[i] - avg_price
        
    return squeeze_on, squeeze_off, momentum

# [Smart Money Concepts (SMC: Market Structure BOS & FVG) 계산기]
@njit
def compute_smc_signals_nb(h, l, c, swing_len=5):
    n = len(c)
    bull_structure = np.zeros(n, dtype=np.bool_)
    bear_structure = np.zeros(n, dtype=np.bool_)
    bull_fvg = np.zeros(n, dtype=np.bool_)
    bear_fvg = np.zeros(n, dtype=np.bool_)
    
    last_pivot_high = np.nan
    last_pivot_low = np.nan
    market_structure = 0  # 1 = Bullish BOS confirmed, -1 = Bearish BOS confirmed
    
    for i in range(swing_len * 2 + 1, n):
        # 1) Pivot High / Low 판정 (과거 swing_len 지점)
        p_idx = i - swing_len
        is_pivot_h = True
        is_pivot_l = True
        for k in range(p_idx - swing_len, p_idx + swing_len + 1):
            if k == p_idx: continue
            if h[k] >= h[p_idx]: is_pivot_h = False
            if l[k] <= l[p_idx]: is_pivot_l = False
            
        if is_pivot_h:
            last_pivot_high = h[p_idx]
        if is_pivot_l:
            last_pivot_low = l[p_idx]
            
        # 2) BOS (Break of Structure): 이전 Pivot 돌파 시 시장 구조 전환
        if not np.isnan(last_pivot_high) and c[i] > last_pivot_high:
            market_structure = 1
        elif not np.isnan(last_pivot_low) and c[i] < last_pivot_low:
            market_structure = -1
            
        if market_structure == 1:
            bull_structure[i] = True
        elif market_structure == -1:
            bear_structure[i] = True
            
        # 3) Fair Value Gap (FVG: 3캔들 불균형 갭)
        if l[i] > h[i-2]:
            bull_fvg[i] = True
        if h[i] < l[i-2]:
            bear_fvg[i] = True
            
    return bull_structure, bear_structure, bull_fvg, bear_fvg

# [RSI (Relative Strength Index) Wilder's RMA 공식 계산기]
@njit
def calc_rsi_pine_nb(c, length=14):
    n = len(c)
    rsi = np.full(n, 50.0)
    if n < length + 1:
        return rsi
    up_sum = 0.0
    dn_sum = 0.0
    for i in range(1, length + 1):
        diff = c[i] - c[i-1]
        if diff > 0:
            up_sum += diff
        else:
            dn_sum += -diff
    avg_gain = up_sum / length
    avg_loss = dn_sum / length
    if avg_loss == 0.0:
        rsi[length] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[length] = 100.0 - (100.0 / (1.0 + rs))
        
    for i in range(length + 1, n):
        diff = c[i] - c[i-1]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (length - 1) + gain) / length
        avg_loss = (avg_loss * (length - 1) + loss) / length
        if avg_loss == 0.0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi

# [ADX (Average Directional Index) Wilder's DMI 공식 계산기]
@njit
def calc_adx_pine_nb(h, l, c, length=14):
    n = len(c)
    adx = np.full(n, 0.0)
    if n < length * 2:
        return adx
    
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        hl = h[i] - l[i]
        hc = abs(h[i] - c[i-1])
        lc = abs(l[i] - c[i-1])
        tr[i] = max(hl, max(hc, lc))
        
        up = h[i] - h[i-1]
        down = l[i-1] - l[i]
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down
            
    sm_tr = np.zeros(n)
    sm_pdm = np.zeros(n)
    sm_mdm = np.zeros(n)
    
    tr_sum = 0.0
    pdm_sum = 0.0
    mdm_sum = 0.0
    for i in range(1, length + 1):
        tr_sum += tr[i]
        pdm_sum += plus_dm[i]
        mdm_sum += minus_dm[i]
        
    sm_tr[length] = tr_sum
    sm_pdm[length] = pdm_sum
    sm_mdm[length] = mdm_sum
    
    dx = np.zeros(n)
    for i in range(length + 1, n):
        sm_tr[i] = sm_tr[i-1] - (sm_tr[i-1] / length) + tr[i]
        sm_pdm[i] = sm_pdm[i-1] - (sm_pdm[i-1] / length) + plus_dm[i]
        sm_mdm[i] = sm_mdm[i-1] - (sm_mdm[i-1] / length) + minus_dm[i]
        
        pdi = 100.0 * sm_pdm[i] / sm_tr[i] if sm_tr[i] != 0 else 0.0
        mdi = 100.0 * sm_mdm[i] / sm_tr[i] if sm_tr[i] != 0 else 0.0
        di_diff = abs(pdi - mdi)
        di_sum = pdi + mdi
        dx[i] = 100.0 * di_diff / di_sum if di_sum != 0 else 0.0
        
    adx_sum = 0.0
    start_adx = length * 2 - 1
    for i in range(length, start_adx + 1):
        adx_sum += dx[i]
    adx[start_adx] = adx_sum / length
    for i in range(start_adx + 1, n):
        adx[i] = (adx[i-1] * (length - 1) + dx[i]) / length
        
    return adx

def run_simulation(df, params, split_ratio=0.70):
    """
    params:
      st_period, st_mult, ema_len, use_ema_filter,
      min_width_pct, use_min_volat,
      tr_ma_len, use_tr_exit,
      use_squeeze, sqz_len, bb_mult, kc_mult,
      use_smc, smc_swing_len, smc_mode,
      use_rsi, rsi_len, rsi_ob, rsi_os, rsi_mode,
      use_adx, adx_len, adx_threshold,
      use_vol, vol_ma_len, vol_mult,
      tp_mode, sl_mode, tp_fixed_pct, sl_fixed_pct, tp_atr_mult, sl_atr_mult,
      max_bars_hold, use_time_exit
    """
    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    o = df['open'].values
    v = df['volume'].values if 'volume' in df.columns else np.ones(len(df))
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
    
    # Squeeze Momentum 지표 계산
    use_squeeze = params.get('use_squeeze', False)
    sqz_len = params.get('sqz_len', 20)
    bb_mult = params.get('bb_mult', 2.0)
    kc_mult = params.get('kc_mult', 1.5)
    sqz_on, sqz_off, mom = compute_squeeze_momentum_nb(h, l, c, length=sqz_len, mult_bb=bb_mult, mult_kc=kc_mult)
    
    # Smart Money Concepts (SMC) 지표 계산
    use_smc = params.get('use_smc', False)
    smc_swing_len = params.get('smc_swing_len', 5)
    smc_mode = params.get('smc_mode', 'Structure')
    bull_struct, bear_struct, bull_fvg, bear_fvg = compute_smc_signals_nb(h, l, c, swing_len=smc_swing_len)
    
    # RSI 지표 계산
    use_rsi = params.get('use_rsi', False)
    rsi_len = params.get('rsi_len', 14)
    rsi_ob = params.get('rsi_ob', 70.0)
    rsi_os = params.get('rsi_os', 30.0)
    rsi_mode = params.get('rsi_mode', 'Boundary')
    rsi_vals = calc_rsi_pine_nb(c, rsi_len)
    
    # ADX 지표 계산
    use_adx = params.get('use_adx', False)
    adx_len = params.get('adx_len', 14)
    adx_threshold = params.get('adx_threshold', 20.0)
    adx_vals = calc_adx_pine_nb(h, l, c, adx_len)
    
    # Volume MA 지표 계산
    use_vol = params.get('use_vol', False)
    vol_ma_len = params.get('vol_ma_len', 20)
    vol_mult = params.get('vol_mult', 1.0)
    vol_ma = pd.Series(v).rolling(vol_ma_len).mean().fillna(0).values
    
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
        
        # Squeeze Momentum 필터 (롱은 모멘텀 양수, 숏은 모멘텀 음수)
        sqz_long_pass = not use_squeeze or (mom[i] > 0)
        sqz_short_pass = not use_squeeze or (mom[i] < 0)
        
        # SMC 필터 (BOS 시장 구조 또는 최근 5봉 FVG)
        if not use_smc:
            smc_long_pass = True
            smc_short_pass = True
        else:
            recent_bull_fvg = False
            recent_bear_fvg = False
            for k in range(max(0, i-4), i+1):
                if bull_fvg[k]: recent_bull_fvg = True
                if bear_fvg[k]: recent_bear_fvg = True
                
            if smc_mode == 'Structure':
                smc_long_pass = bull_struct[i]
                smc_short_pass = bear_struct[i]
            elif smc_mode == 'FVG':
                smc_long_pass = recent_bull_fvg
                smc_short_pass = recent_bear_fvg
            else: # Both
                smc_long_pass = bull_struct[i] and recent_bull_fvg
                smc_short_pass = bear_struct[i] and recent_bear_fvg
                
        # RSI 필터
        if not use_rsi:
            rsi_long_pass = True
            rsi_short_pass = True
        else:
            if rsi_mode == 'Boundary':
                rsi_long_pass = (rsi_vals[i] < rsi_ob)
                rsi_short_pass = (rsi_vals[i] > rsi_os)
            else: # Momentum
                rsi_long_pass = (rsi_vals[i] > 50.0)
                rsi_short_pass = (rsi_vals[i] < 50.0)
                
        # ADX 추세 강도 필터
        adx_pass = not use_adx or (adx_vals[i] >= adx_threshold)
        
        # Volume 거래량 수급 필터
        vol_pass = not use_vol or (v[i] >= vol_ma[i] * vol_mult)
        
        if bull_flip and long_regime and v_ok and sqz_long_pass and smc_long_pass and rsi_long_pass and adx_pass and vol_pass:
            long_raw[i] = True
        if bear_flip and short_regime and v_ok and sqz_short_pass and smc_short_pass and rsi_short_pass and adx_pass and vol_pass:
            short_raw[i] = True
            
    # Look-ahead Bias 방지: 다음 봉 시가 체결 (shift 1)
    long_sig = np.zeros(n, dtype=np.bool_)
    short_sig = np.zeros(n, dtype=np.bool_)
    long_sig[1:] = long_raw[:-1]
    short_sig[1:] = short_raw[:-1]
    
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
