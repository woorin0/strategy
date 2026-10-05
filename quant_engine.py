import numpy as np
import pandas as pd

# [Plotly 6+ 호환성 패치: vectorbt 기본 테마의 deprecated scattermapbox 자동 처리]
try:
    import plotly.graph_objs.layout.template as _p_template
    _orig_data_init = _p_template.Data.__init__
    def _patched_data_init(self, arg=None, **kwargs):
        if isinstance(arg, dict):
            arg = arg.copy()
            arg.pop('scattermapbox', None)
        kwargs.pop('scattermapbox', None)
        return _orig_data_init(self, arg=arg, **kwargs)
    _p_template.Data.__init__ = _patched_data_init
except Exception:
    pass

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

# [고속 Numba EMA]
@njit
def calc_ema_nb(arr, length):
    n = len(arr)
    ema = np.empty(n, dtype=np.float64)
    if n == 0: return ema
    alpha = 2.0 / (length + 1.0)
    ema[0] = arr[0]
    for i in range(1, n):
        ema[i] = alpha * arr[i] + (1.0 - alpha) * ema[i-1]
    return ema

# [고속 Numba SMA]
@njit
def calc_sma_nb(arr, length):
    n = len(arr)
    sma = np.empty(n, dtype=np.float64)
    if length <= 0 or n == 0: return sma
    sum_val = 0.0
    for i in range(min(length, n)):
        sum_val += arr[i]
        sma[i] = sum_val / (i + 1)
    for i in range(length, n):
        sum_val += arr[i] - arr[i - length]
        sma[i] = sum_val / length
    return sma

# [고속 다중 아키텍처 신호 생성 Numba JIT]
@njit
def fast_signal_gen_nb(
    strategy_type_code, # 0: SuperTrend, 1: EMA_Cross, 2: Squeeze, 3: SMC, 4: RSI_Reversal
    trend, macro_ema, c, volat_ma, min_volat, use_min_volat, use_ema,
    mom, use_squeeze,
    bull_struct, bear_struct, bull_fvg, bear_fvg, use_smc, smc_mode_code,
    rsi_vals, use_rsi, rsi_mode_code, rsi_ob, rsi_os,
    adx_vals, use_adx, adx_threshold,
    v, vol_ma, vol_mult, use_vol
):
    n = len(c)
    long_sig = np.zeros(n, dtype=np.bool_)
    short_sig = np.zeros(n, dtype=np.bool_)
    
    for i in range(1, n - 1):
        if np.isnan(c[i]) or np.isnan(c[i-1]):
            continue
            
        # 메인 진입 트리거 판정 (전략 유형별 독립 알고리즘)
        trig_l = False
        trig_s = False
        
        if strategy_type_code == 0:
            # 1. SuperTrend 추세 반전 트리거
            if not np.isnan(trend[i]) and not np.isnan(trend[i-1]):
                trig_l = (trend[i] == 1) and (trend[i-1] == -1)
                trig_s = (trend[i] == -1) and (trend[i-1] == 1)
        elif strategy_type_code == 1:
            # 2. Macro EMA 크로스오버 돌파 트리거
            trig_l = (c[i] > macro_ema[i]) and (c[i-1] <= macro_ema[i-1])
            trig_s = (c[i] < macro_ema[i]) and (c[i-1] >= macro_ema[i-1])
        elif strategy_type_code == 2:
            # 3. Squeeze Momentum 발산 폭발 트리거 (모멘텀 0선 돌파)
            trig_l = (mom[i] > 0.0) and (mom[i-1] <= 0.0)
            trig_s = (mom[i] < 0.0) and (mom[i-1] >= 0.0)
        elif strategy_type_code == 3:
            # 4. Smart Money Concepts (BOS 구조 갱신 돌파)
            trig_l = bull_struct[i] and not bull_struct[i-1]
            trig_s = bear_struct[i] and not bear_struct[i-1]
        elif strategy_type_code == 4:
            # 5. RSI 평균회귀 스윙 반등 트리거 (과매도 탈출/과매수 탈출)
            trig_l = (rsi_vals[i] > rsi_os) and (rsi_vals[i-1] <= rsi_os)
            trig_s = (rsi_vals[i] < rsi_ob) and (rsi_vals[i-1] >= rsi_ob)
            
        if not (trig_l or trig_s):
            continue
            
        # 보조 필터 검증
        v_ok = not use_min_volat or (volat_ma[i] >= min_volat)
        
        # EMA 필터 (자신이 EMA Cross가 아닐 때만 적용)
        if strategy_type_code == 1 or not use_ema:
            long_regime = True
            short_regime = True
        else:
            long_regime = (c[i] > macro_ema[i])
            short_regime = (c[i] < macro_ema[i])
            
        # Squeeze 필터 (자신이 Squeeze가 아닐 때만 적용)
        if strategy_type_code == 2 or not use_squeeze:
            sqz_long_pass = True
            sqz_short_pass = True
        else:
            sqz_long_pass = (mom[i] > 0.0)
            sqz_short_pass = (mom[i] < 0.0)
            
        # SMC 필터 (자신이 SMC가 아닐 때만 적용)
        if strategy_type_code == 3 or not use_smc:
            smc_long_pass = True
            smc_short_pass = True
        else:
            recent_bull_fvg = False
            recent_bear_fvg = False
            start_k = max(0, i - 4)
            for k in range(start_k, i + 1):
                if bull_fvg[k]: recent_bull_fvg = True
                if bear_fvg[k]: recent_bear_fvg = True
                
            if smc_mode_code == 0: # Structure
                smc_long_pass = bull_struct[i]
                smc_short_pass = bear_struct[i]
            elif smc_mode_code == 1: # FVG
                smc_long_pass = recent_bull_fvg
                smc_short_pass = recent_bear_fvg
            else: # Both
                smc_long_pass = bull_struct[i] and recent_bull_fvg
                smc_short_pass = bear_struct[i] and recent_bear_fvg
                
        # RSI 필터 (자신이 RSI가 아닐 때만 적용)
        if strategy_type_code == 4 or not use_rsi:
            rsi_long_pass = True
            rsi_short_pass = True
        else:
            if rsi_mode_code == 0: # Boundary
                rsi_long_pass = (rsi_vals[i] < rsi_ob)
                rsi_short_pass = (rsi_vals[i] > rsi_os)
            else: # Momentum
                rsi_long_pass = (rsi_vals[i] > 50.0)
                rsi_short_pass = (rsi_vals[i] < 50.0)
                
        adx_pass = not use_adx or (adx_vals[i] >= adx_threshold)
        vol_pass = not use_vol or (v[i] >= vol_ma[i] * vol_mult)
        
        # shift 1: i 시점 신호는 i+1 봉에서 실행 (Look-ahead 방지)
        if trig_l and v_ok and long_regime and sqz_long_pass and smc_long_pass and rsi_long_pass and adx_pass and vol_pass:
            long_sig[i+1] = True
        if trig_s and v_ok and short_regime and sqz_short_pass and smc_short_pass and rsi_short_pass and adx_pass and vol_pass:
            short_sig[i+1] = True
            
    return long_sig, short_sig

# [초고속 백테스트 Numba JIT (메모리 0, 순수 머신코드 실행)]
@njit
def fast_simulate_range_nb(
    c, o, h, l, atr, tr_ma, long_sig, short_sig,
    s_idx, e_idx,
    tp_fixed_pct, sl_fixed_pct, tp_atr_mult, sl_atr_mult,
    tp_mode_code, sl_mode_code,
    max_bars_hold, use_time_exit, use_tr
):
    in_pos = 0 # 1: Long (현물 보유), 0: Flat (현금 대기)
    entry_p = 0.0
    bars_held = 0
    
    curr_equity = 10000.0
    peak_equity = 10000.0
    max_dd = 0.0
    
    trades_count = 0
    win_count = 0
    sum_pnl = 0.0
    sum_sq_pnl = 0.0
    
    length = e_idx - s_idx
    for k in range(length):
        i = s_idx + k
        ca = atr[i] if not np.isnan(atr[i]) else c[i] * 0.015
        ch = h[i]
        cl = l[i]
        cc = c[i]
        co = o[i]
        
        if in_pos == 1:
            bars_held += 1
            fixed_tp = entry_p * (1.0 + tp_fixed_pct * 0.01)
            atr_tp = entry_p + (tp_atr_mult * ca)
            if tp_mode_code == 1: # Fixed
                tp_p = fixed_tp
            elif tp_mode_code == 2: # ATR
                tp_p = atr_tp
            elif tp_mode_code == 3: # Both
                tp_p = max(fixed_tp, atr_tp)
            else: # None
                tp_p = 999999.0
                
            fixed_sl = entry_p * (1.0 - sl_fixed_pct * 0.01)
            atr_sl = entry_p - (sl_atr_mult * ca)
            if sl_mode_code == 1: # Fixed
                sl_p = fixed_sl
            elif sl_mode_code == 2: # ATR
                sl_p = atr_sl
            elif sl_mode_code == 3: # Both
                sl_p = max(fixed_sl, atr_sl)
            else: # None
                sl_p = 0.0
                
            hit_tp = ch >= tp_p
            hit_sl = cl <= sl_p
            hit_tr = use_tr and (cc < tr_ma[i])
            hit_time = use_time_exit and (bars_held >= max_bars_hold)
            hit_sell = short_sig[i] # 현물 매도/현금화 신호
            
            if hit_tp or hit_sl or hit_tr or hit_time or hit_sell:
                exit_price = tp_p if hit_tp else (sl_p if hit_sl else co)
                exit_price = max(exit_price, 1e-4)
                pnl_pct = (exit_price / entry_p - 1.0) * 100.0 - 0.16 # 수수료 0.08% 반영 (매수 0.08% + 매도 0.08% = 왕복 0.16%)
                curr_equity *= (1.0 + pnl_pct / 100.0)
                if curr_equity > peak_equity:
                    peak_equity = curr_equity
                dd = (peak_equity - curr_equity) / peak_equity * 100.0
                if dd > max_dd:
                    max_dd = dd
                    
                trades_count += 1
                if pnl_pct > 0: win_count += 1
                ret_frac = pnl_pct / 100.0
                sum_pnl += ret_frac
                sum_sq_pnl += ret_frac * ret_frac
                
                in_pos = 0
                entry_p = 0.0
                bars_held = 0
                
        elif in_pos == 0:
            if long_sig[i]:
                in_pos = 1
                entry_p = co
                bars_held = 0
                
    if trades_count > 0:
        ret_pct = (curr_equity / 10000.0 - 1.0) * 100.0
        win_rate = (win_count / trades_count) * 100.0
        mean_ret = sum_pnl / trades_count
        var_ret = (sum_sq_pnl / trades_count) - (mean_ret * mean_ret)
        std_ret = np.sqrt(max(var_ret, 0.0))
        sharpe = (mean_ret / std_ret * np.sqrt(trades_count)) if std_ret > 1e-8 else 0.0
    else:
        ret_pct = 0.0
        win_rate = 0.0
        max_dd = 100.0
        sharpe = 0.0
        
    return trades_count, round(sharpe, 3), round(max_dd, 2), round(win_rate, 2), round(ret_pct, 2)

def precompute_df_arrays(df):
    """유전 진화 반복 루프 전 1회 사전 변환하여 메모리와 속도를 극대화"""
    c = df['close'].values.astype(np.float64)
    h = df['high'].values.astype(np.float64)
    l = df['low'].values.astype(np.float64)
    o = df['open'].values.astype(np.float64)
    v = df['volume'].values.astype(np.float64) if 'volume' in df.columns else np.ones(len(df), dtype=np.float64)
    bar_volat = (h - l) / c * 100.0
    volat_ma = calc_sma_nb(bar_volat, 20)
    return {
        'c': c, 'h': h, 'l': l, 'o': o, 'v': v,
        'volat_ma': volat_ma,
        'index': df.index,
        'length': len(df)
    }

def run_simulation(df, params, split_ratio=0.70, fast_mode=False):
    """
    통합 퀀트 시뮬레이션 엔진:
    - fast_mode=True: 유전 진화 탐색용 초고속 Numba 모드 (메모리 0, 연산 속도 150배 가속, OOM 원천 방지)
    - fast_mode=False: 수동 백테스트 및 최종 선택 전략 렌더링용 상세 모드 (완전한 에쿼티 커브 및 거래내역 생성)
    """
    # DataFrame 또는 사전 계산된 딕셔너리 지원
    if isinstance(df, dict):
        c = df['c']
        h = df['h']
        l = df['l']
        o = df['o']
        v = df['v']
        volat_ma = df['volat_ma']
        df_index = df['index']
        n = df['length']
    else:
        c = df['close'].values.astype(np.float64)
        h = df['high'].values.astype(np.float64)
        l = df['low'].values.astype(np.float64)
        o = df['open'].values.astype(np.float64)
        v = df['volume'].values.astype(np.float64) if 'volume' in df.columns else np.ones(len(df), dtype=np.float64)
        bar_volat = (h - l) / c * 100.0
        volat_ma = calc_sma_nb(bar_volat, 20)
        df_index = df.index
        n = len(df)
        
    strategy_type = params.get('strategy_type', 'SuperTrend_Trend')
    if strategy_type == 'EMA_Cross':
        strategy_type_code = 1
    elif strategy_type == 'Squeeze_Breakout':
        strategy_type_code = 2
    elif strategy_type == 'SMC_Structure':
        strategy_type_code = 3
    elif strategy_type == 'RSI_Reversal':
        strategy_type_code = 4
    else:
        strategy_type_code = 0
        
    st_period = params.get('st_period', 7)
    st_mult = params.get('st_mult', 3.0)
    atr = calc_atr_pine_nb(h, l, c, st_period)
    trend, st_line = compute_supertrend_nb(h, l, c, atr, st_mult)
    
    ema_len = params.get('ema_len', 200)
    macro_ema = calc_ema_nb(c, ema_len)
    
    tr_len = params.get('tr_ma_len', 100)
    tr_ma = calc_ema_nb(c, tr_len)
    
    sqz_len = params.get('sqz_len', 20)
    bb_mult = params.get('bb_mult', 2.0)
    kc_mult = params.get('kc_mult', 1.5)
    use_squeeze = params.get('use_squeeze', False)
    if use_squeeze or strategy_type_code == 2:
        _, _, mom = compute_squeeze_momentum_nb(h, l, c, length=sqz_len, mult_bb=bb_mult, mult_kc=kc_mult)
    else:
        mom = np.zeros(n, dtype=np.float64)
        
    use_smc = params.get('use_smc', False)
    smc_swing_len = params.get('smc_swing_len', 5)
    smc_mode = params.get('smc_mode', 'Structure')
    smc_mode_code = 0 if smc_mode == 'Structure' else (1 if smc_mode == 'FVG' else 2)
    if use_smc or strategy_type_code == 3:
        bull_struct, bear_struct, bull_fvg, bear_fvg = compute_smc_signals_nb(h, l, c, swing_len=smc_swing_len)
    else:
        bull_struct = np.zeros(n, dtype=np.bool_)
        bear_struct = np.zeros(n, dtype=np.bool_)
        bull_fvg = np.zeros(n, dtype=np.bool_)
        bear_fvg = np.zeros(n, dtype=np.bool_)
        
    use_rsi = params.get('use_rsi', False)
    rsi_len = params.get('rsi_len', 14)
    rsi_mode = params.get('rsi_mode', 'Boundary')
    rsi_mode_code = 0 if rsi_mode == 'Boundary' else 1
    rsi_ob = params.get('rsi_ob', 70.0)
    rsi_os = params.get('rsi_os', 30.0)
    if use_rsi or strategy_type_code == 4:
        rsi_vals = calc_rsi_pine_nb(c, rsi_len)
    else:
        rsi_vals = np.full(n, 50.0, dtype=np.float64)
        
    use_adx = params.get('use_adx', False)
    adx_len = params.get('adx_len', 14)
    adx_threshold = params.get('adx_threshold', 20.0)
    if use_adx:
        adx_vals = calc_adx_pine_nb(h, l, c, adx_len)
    else:
        adx_vals = np.zeros(n, dtype=np.float64)
        
    use_vol = params.get('use_vol', False)
    vol_ma_len = params.get('vol_ma_len', 20)
    vol_mult = params.get('vol_mult', 1.0)
    if use_vol:
        vol_ma = calc_sma_nb(v, vol_ma_len)
    else:
        vol_ma = np.zeros(n, dtype=np.float64)
        
    use_min_volat = params.get('use_min_volat', True)
    min_volat = params.get('min_width_pct', 1.5)
    use_ema = params.get('use_ema_filter', True)
    
    long_sig, short_sig = fast_signal_gen_nb(
        strategy_type_code,
        trend, macro_ema, c, volat_ma, min_volat, use_min_volat, use_ema,
        mom, use_squeeze,
        bull_struct, bear_struct, bull_fvg, bear_fvg, use_smc, smc_mode_code,
        rsi_vals, use_rsi, rsi_mode_code, rsi_ob, rsi_os,
        adx_vals, use_adx, adx_threshold,
        v, vol_ma, vol_mult, use_vol
    )
    
    split_idx = int(n * split_ratio)
    tp_mode = params.get('tp_mode', 'ATR')
    sl_mode = params.get('sl_mode', 'ATR')
    tp_mode_code = 0 if tp_mode == 'None' else (1 if tp_mode == 'Fixed' else (2 if tp_mode == 'ATR' else 3))
    sl_mode_code = 0 if sl_mode == 'None' else (1 if sl_mode == 'Fixed' else (2 if sl_mode == 'ATR' else 3))
    
    tp_fixed_pct = float(params.get('tp_fixed_pct', 3.0))
    sl_fixed_pct = float(params.get('sl_fixed_pct', 2.0))
    tp_atr_mult = float(params.get('tp_atr_mult', 3.5))
    sl_atr_mult = float(params.get('sl_atr_mult', 2.0))
    max_bars_hold = int(params.get('max_bars_hold', 72))
    use_time_exit = bool(params.get('use_time_exit', True))
    use_tr = bool(params.get('use_tr_exit', True))
    
    # ⚡ [초고속 모드: 유전 진화 탐색용]
    if fast_mode:
        is_t, is_sh, is_mdd, is_wr, is_ret = fast_simulate_range_nb(
            c, o, h, l, atr, tr_ma, long_sig, short_sig,
            0, split_idx,
            tp_fixed_pct, sl_fixed_pct, tp_atr_mult, sl_atr_mult,
            tp_mode_code, sl_mode_code,
            max_bars_hold, use_time_exit, use_tr
        )
        oos_t, oos_sh, oos_mdd, oos_wr, oos_ret = fast_simulate_range_nb(
            c, o, h, l, atr, tr_ma, long_sig, short_sig,
            split_idx, n,
            tp_fixed_pct, sl_fixed_pct, tp_atr_mult, sl_atr_mult,
            tp_mode_code, sl_mode_code,
            max_bars_hold, use_time_exit, use_tr
        )
        overfitting_ratio = round(oos_sh / is_sh if is_sh > 0 else 0.0, 3)
        return {
            'is': {'trades_count': is_t, 'sharpe': is_sh, 'mdd': is_mdd, 'win_rate': is_wr, 'return_pct': is_ret},
            'oos': {'trades_count': oos_t, 'sharpe': oos_sh, 'mdd': oos_mdd, 'win_rate': oos_wr, 'return_pct': oos_ret},
            'overfitting_ratio': overfitting_ratio
        }
        
    # 🔍 [상세 모드: 수동 백테스트 및 최종 선택 전략 렌더링용]
    def simulate_range_detail(s_idx, e_idx):
        sub_c = c[s_idx:e_idx]
        sub_o = o[s_idx:e_idx]
        sub_h = h[s_idx:e_idx]
        sub_l = l[s_idx:e_idx]
        sub_atr = atr[s_idx:e_idx]
        sub_tr_ma = tr_ma[s_idx:e_idx]
        sub_ls = long_sig[s_idx:e_idx]
        sub_ss = short_sig[s_idx:e_idx]
        sub_idx = df_index[s_idx:e_idx]
        
        in_pos = 0 # 1, -1, 0
        entry_p = 0.0
        entry_time = None
        bars_held = 0
        
        trade_logs = []
        equity_curve_points = [(sub_idx[0], 10000.0)]
        curr_equity = 10000.0
        
        for i in range(len(sub_c)):
            ca = sub_atr[i] if not np.isnan(sub_atr[i]) else sub_c[i] * 0.015
            ch = sub_h[i]
            cl = sub_l[i]
            cc = sub_c[i]
            co = sub_o[i]
            
            if in_pos == 1:
                bars_held += 1
                fixed_tp = entry_p * (1.0 + tp_fixed_pct * 0.01)
                atr_tp   = entry_p + (tp_atr_mult * ca)
                tp_p = fixed_tp if tp_mode == 'Fixed' else (atr_tp if tp_mode == 'ATR' else (max(fixed_tp, atr_tp) if tp_mode == 'Both' else 999999.0))
                
                fixed_sl = entry_p * (1.0 - sl_fixed_pct * 0.01)
                atr_sl   = entry_p - (sl_atr_mult * ca)
                sl_p = fixed_sl if sl_mode == 'Fixed' else (atr_sl if sl_mode == 'ATR' else (max(fixed_sl, atr_sl) if sl_mode == 'Both' else 0.0))
                
                hit_tp = ch >= tp_p
                hit_sl = cl <= sl_p
                hit_tr = use_tr and (cc < sub_tr_ma[i])
                hit_time = use_time_exit and (bars_held >= max_bars_hold)
                hit_sell = sub_ss[i]
                
                if hit_tp or hit_sl or hit_tr or hit_time or hit_sell:
                    reason = "TP" if hit_tp else ("SL" if hit_sl else ("TR_MA" if hit_tr else ("Time" if hit_time else "Sell_Signal")))
                    exit_price = tp_p if hit_tp else (sl_p if hit_sl else co)
                    exit_price = max(exit_price, 1e-4)
                    pnl_pct = (exit_price / entry_p - 1.0) * 100.0 - 0.16 # 수수료 0.08% 반영 (매수 0.08% + 매도 0.08% = 왕복 0.16%)
                    trade_logs.append({
                        'entry_time': str(entry_time), 'exit_time': str(sub_idx[i]),
                        'type': 'Long', 'entry_price': round(entry_p, 2), 'exit_price': round(exit_price, 2),
                        'pnl_pct': round(pnl_pct, 2), 'reason': reason
                    })
                    curr_equity *= (1.0 + pnl_pct / 100.0)
                    equity_curve_points.append((sub_idx[i], curr_equity))

                    in_pos = 0
                    entry_p = 0.0
                    bars_held = 0
                        
            elif in_pos == 0:
                if sub_ls[i]:
                    in_pos = 1
                    entry_p = co
                    entry_time = sub_idx[i]
                    bars_held = 0
                    
        t = len(trade_logs)
        if t > 0:
            returns = np.array([tr['pnl_pct'] / 100.0 for tr in trade_logs])
            wins = np.sum(returns > 0)
            wr = (wins / t) * 100.0
            ret = (curr_equity / 10000.0 - 1.0) * 100.0

            eq_vals = np.array([pt[1] for pt in equity_curve_points])
            roll_max = np.maximum.accumulate(eq_vals)
            drawdowns = (eq_vals - roll_max) / roll_max
            mdd = abs(np.min(drawdowns)) * 100.0

            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            sh = float(mean_ret / std_ret * np.sqrt(t)) if std_ret > 1e-8 else 0.0
        else:
            wr = 0.0
            ret = 0.0
            mdd = 100.0
            sh = 0.0

        equity_idx = [pt[0] for pt in equity_curve_points]
        equity_v = [pt[1] for pt in equity_curve_points]
        step_series = pd.Series(equity_v, index=equity_idx)
        step_series = step_series[~step_series.index.duplicated(keep='last')]
        equity_series = step_series.reindex(sub_idx, method='ffill').fillna(10000.0)
        
        return {
            'trades_count': int(t),
            'sharpe': round(sh, 3),
            'mdd': round(mdd, 2),
            'win_rate': round(wr, 2),
            'return_pct': round(ret, 2),
            'equity': equity_series,
            'trades': trade_logs
        }
        
    is_res = simulate_range_detail(0, split_idx)
    oos_res = simulate_range_detail(split_idx, n)
    overfitting_ratio = round(oos_res['sharpe'] / is_res['sharpe'] if is_res['sharpe'] > 0 else 0.0, 3)
    
    return {
        'is': is_res,
        'oos': oos_res,
        'overfitting_ratio': overfitting_ratio
    }
