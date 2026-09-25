import pandas as pd
import numpy as np
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from quant_engine import run_simulation

def generate_pine_script_v6(strategy_title, params, metrics_summary):
    """
    최적화된 파라미터(SMC, Squeeze Momentum 포함)를 바탕으로 공식 Pine Script v6 완전한 코드를 동적 합성
    """
    st_period = params.get('st_period', 7)
    st_mult = params.get('st_mult', 3.0)
    use_ema = params.get('use_ema_filter', True)
    ema_len = params.get('ema_len', 200)
    use_min_volat = params.get('use_min_volat', True)
    min_width = params.get('min_width_pct', 1.5)
    use_tr = params.get('use_tr_exit', True)
    tr_len = params.get('tr_ma_len', 100)
    
    # Squeeze Momentum 파라미터
    use_sqz = params.get('use_squeeze', False)
    sqz_len = params.get('sqz_len', 20)
    bb_mult = params.get('bb_mult', 2.0)
    kc_mult = params.get('kc_mult', 1.5)
    
    # SMC 파라미터
    use_smc = params.get('use_smc', False)
    smc_swing = params.get('smc_swing_len', 5)
    smc_mode = params.get('smc_mode', 'Structure')
    
    # RSI 파라미터
    use_rsi = params.get('use_rsi', False)
    rsi_len = params.get('rsi_len', 14)
    rsi_mode = params.get('rsi_mode', 'Boundary')
    rsi_ob = params.get('rsi_ob', 70.0)
    rsi_os = params.get('rsi_os', 30.0)

    # ADX 파라미터
    use_adx = params.get('use_adx', False)
    adx_len = params.get('adx_len', 14)
    adx_threshold = params.get('adx_threshold', 20.0)

    # Volume MA 파라미터
    use_vol = params.get('use_vol', False)
    vol_len = params.get('vol_ma_len', 20)
    vol_mult = params.get('vol_mult', 1.0)
    
    tp_mode = params.get('tp_mode', 'ATR')
    sl_mode = params.get('sl_mode', 'ATR')
    tp_fixed = params.get('tp_fixed_pct', 3.0)
    sl_fixed = params.get('sl_fixed_pct', 2.0)
    tp_atr = params.get('tp_atr_mult', 3.5)
    sl_atr = params.get('sl_atr_mult', 2.0)
    use_time = params.get('use_time_exit', True)
    max_bars = params.get('max_bars_hold', 72)
    
    code = f'''//@version=6
// 🤖 AI Autonomous Quantitative Strategy Generator v6.0
// [AI Engine Report]
// - Symbol: {metrics_summary.get('symbol', 'BTC/USDT')} ({metrics_summary.get('timeframe', '1h')})
// - OOS Sharpe: {metrics_summary.get('oos_sharpe', 0.0)} | OOS Return: {metrics_summary.get('oos_return', 0.0)}%
// - OOS MDD: {metrics_summary.get('oos_mdd', 0.0)}% | OOS Win Rate: {metrics_summary.get('oos_win_rate', 0.0)}%
strategy("{strategy_title}", 
         overlay=true, 
         initial_capital=10000, 
         default_qty_type=strategy.percent_of_equity, 
         default_qty_value=100, 
         commission_type=strategy.commission.percent, 
         commission_value=0.05, 
         process_orders_on_close=true)

// ==========================================
// 1. INPUT PARAMETERS (AI Optimized Parameters)
// ==========================================
group_st = "1. SuperTrend Engine"
st_period = input.int({st_period}, "SuperTrend ATR Period", minval=1, group=group_st)
st_mult   = input.float({st_mult}, "SuperTrend Factor/Multiplier", minval=0.1, step=0.1, group=group_st)

group_filter = "2. Macro Regime & Volatility Filter"
use_ema_filter = input.bool({str(use_ema).lower()}, "Use Macro Trend EMA Filter", group=group_filter)
ema_len        = input.int({ema_len}, "Macro EMA Length", minval=10, group=group_filter)
use_min_volat  = input.bool({str(use_min_volat).lower()}, "Use Min Width (Volatility Filter)", group=group_filter)
min_width_pct  = input.float({min_width}, "Min Volatility Width (%)", minval=0.0, step=0.1, group=group_filter)

group_sqz = "3. Squeeze Momentum (LazyBear)"
use_squeeze = input.bool({str(use_sqz).lower()}, "Enable Squeeze Momentum Filter", group=group_sqz)
sqz_len     = input.int({sqz_len}, "Squeeze Length", minval=5, group=group_sqz)
bb_mult     = input.float({bb_mult}, "BB StdDev Multiplier", minval=0.5, step=0.1, group=group_sqz)
kc_mult     = input.float({kc_mult}, "KC ATR Multiplier", minval=0.5, step=0.1, group=group_sqz)

group_smc = "4. Smart Money Concepts (SMC)"
use_smc       = input.bool({str(use_smc).lower()}, "Enable Smart Money Concepts Filter", group=group_smc)
smc_swing_len = input.int({smc_swing}, "SMC Swing Length (Pivot)", minval=2, group=group_smc)
smc_mode      = input.string("{smc_mode}", "SMC Validation Mode", options=["Structure", "FVG", "Both"], group=group_smc)

group_rsi = "5. RSI (Relative Strength Index) Filter"
use_rsi_filter = input.bool({str(use_rsi).lower()}, "Enable RSI Filter", group=group_rsi)
rsi_len        = input.int({rsi_len}, "RSI Length", minval=1, group=group_rsi)
rsi_mode       = input.string("{rsi_mode}", "RSI Filter Mode", options=["Boundary", "Momentum"], group=group_rsi)
rsi_ob         = input.float({rsi_ob}, "Overbought Level (Max for Long)", minval=50.0, maxval=95.0, group=group_rsi)
rsi_os         = input.float({rsi_os}, "Oversold Level (Min for Short)", minval=5.0, maxval=50.0, group=group_rsi)

group_adx = "6. ADX (Trend Strength) Filter"
use_adx_filter = input.bool({str(use_adx).lower()}, "Enable ADX Filter", group=group_adx)
adx_len        = input.int({adx_len}, "ADX Length", minval=1, group=group_adx)
adx_threshold  = input.float({adx_threshold}, "Min ADX Trend Strength", minval=5.0, step=1.0, group=group_adx)

group_vol = "7. Volume Confirmation Filter"
use_vol_filter = input.bool({str(use_vol).lower()}, "Enable Volume MA Filter", group=group_vol)
vol_ma_len     = input.int({vol_len}, "Volume MA Length", minval=1, group=group_vol)
vol_mult       = input.float({vol_mult}, "Volume Multiplier", minval=0.5, step=0.1, group=group_vol)

group_trma = "8. Trend Reversal MA (TR MA Emergency Exit)"
use_tr_exit  = input.bool({str(use_tr).lower()}, "Enable TR MA Exit", group=group_trma)
tr_ma_type   = input.string("EMA", "TR MA Type", options=["SMA", "EMA", "RMA", "WMA"], group=group_trma)
tr_ma_len    = input.int({tr_len}, "TR MA Length", minval=10, group=group_trma)

group_tpsl = "9. Hybrid Take Profit & Stop Loss"
tp_mode      = input.string("{tp_mode}", "TP Price Mode", options=["None", "Fixed", "ATR", "Both"], group=group_tpsl)
sl_mode      = input.string("{sl_mode}", "SL Price Mode", options=["None", "Fixed", "ATR", "Both"], group=group_tpsl)
tp_fixed_pct = input.float({tp_fixed}, "Fixed Take Profit (%)", minval=0.1, step=0.1, group=group_tpsl)
sl_fixed_pct = input.float({sl_fixed}, "Fixed Stop Loss (%)", minval=0.1, step=0.1, group=group_tpsl)
tp_atr_mult  = input.float({tp_atr}, "TP ATR Multiplier", minval=0.5, step=0.1, group=group_tpsl)
sl_atr_mult  = input.float({sl_atr}, "SL ATR Multiplier", minval=0.5, step=0.1, group=group_tpsl)

group_time = "10. Time Expiry Exit"
use_time_exit = input.bool({str(use_time).lower()}, "Enable Time Expiry Exit", group=group_time)
max_bars_hold = input.int({max_bars}, "Max Holding Bars (Hours)", minval=1, group=group_time)

// ==========================================
// 2. HELPER FUNCTIONS & INDICATORS
// ==========================================
f_ma(source, length, type) =>
    type == "SMA" ? ta.sma(source, length) :
    type == "EMA" ? ta.ema(source, length) :
    type == "RMA" ? ta.rma(source, length) :
    type == "WMA" ? ta.wma(source, length) : na

macro_ema = ta.ema(close, ema_len)
[st_line, st_dir] = ta.supertrend(st_mult, st_period)
atr_val = ta.atr(14)

bar_volat_pct = ((high - low) / math.max(close, syminfo.mintick)) * 100
volat_ma = ta.sma(bar_volat_pct, 20)
volat_pass = not use_min_volat or (volat_ma >= min_width_pct)
tr_ma = f_ma(close, tr_ma_len, tr_ma_type)

// --- Squeeze Momentum (LazyBear 공식) ---
bb_basis = ta.sma(close, sqz_len)
bb_dev = bb_mult * ta.stdev(close, sqz_len)
bb_up = bb_basis + bb_dev
bb_dn = bb_basis - bb_dev

kc_tr = ta.rma(ta.tr, sqz_len)
kc_up = bb_basis + kc_mult * kc_tr
kc_dn = bb_basis - kc_mult * kc_tr

sqz_on = (bb_dn > kc_dn) and (bb_up < kc_up)
sqz_off = (bb_dn < kc_dn) and (bb_up > kc_up)
highest_h = ta.highest(high, sqz_len)
lowest_l = ta.lowest(low, sqz_len)
sqz_mom = ta.linreg(close - math.avg(math.avg(highest_h, lowest_l), bb_basis), sqz_len, 0)

sqz_long_pass  = not use_squeeze or (sqz_mom > 0)
sqz_short_pass = not use_squeeze or (sqz_mom < 0)

// --- Smart Money Concepts (BOS & FVG) ---
p_high = ta.pivothigh(high, smc_swing_len, smc_swing_len)
p_low  = ta.pivotlow(low, smc_swing_len, smc_swing_len)
var float last_p_high = na
var float last_p_low = na
if not na(p_high)
    last_p_high := p_high
if not na(p_low)
    last_p_low := p_low

var int market_structure = 0
if not na(last_p_high) and close > last_p_high
    market_structure := 1
else if not na(last_p_low) and close < last_p_low
    market_structure := -1

bull_structure = (market_structure == 1)
bear_structure = (market_structure == -1)

bull_fvg = low > high[2]
bear_fvg = high < low[2]
var int last_bull_fvg_bar = -999
var int last_bear_fvg_bar = -999
if bull_fvg
    last_bull_fvg_bar := bar_index
if bear_fvg
    last_bear_fvg_bar := bar_index

recent_bull_fvg = (bar_index - last_bull_fvg_bar) <= 5
recent_bear_fvg = (bar_index - last_bear_fvg_bar) <= 5

smc_long_pass  = not use_smc or (smc_mode == "Structure" ? bull_structure : smc_mode == "FVG" ? recent_bull_fvg : (bull_structure and recent_bull_fvg))
smc_short_pass = not use_smc or (smc_mode == "Structure" ? bear_structure : smc_mode == "FVG" ? recent_bear_fvg : (bear_structure and recent_bear_fvg))

// --- RSI (Relative Strength Index) ---
rsi_val = ta.rsi(close, rsi_len)
rsi_long_pass  = not use_rsi_filter or (rsi_mode == "Boundary" ? (rsi_val < rsi_ob) : (rsi_val > 50.0))
rsi_short_pass = not use_rsi_filter or (rsi_mode == "Boundary" ? (rsi_val > rsi_os) : (rsi_val < 50.0))

// --- ADX (Average Directional Index) ---
[diplus, diminus, adx_val] = ta.dmi(adx_len, adx_len)
adx_pass = not use_adx_filter or (adx_val >= adx_threshold)

// --- Volume MA Filter ---
vol_ma = ta.sma(volume, vol_ma_len)
vol_pass = not use_vol_filter or (volume >= vol_ma * vol_mult)

// ==========================================
// 3. REGIME & TRIGGER LOGIC
// ==========================================
bull_flip = (st_dir == -1) and (st_dir[1] == 1)
bear_flip = (st_dir == 1) and (st_dir[1] == -1)

long_regime  = not use_ema_filter or (close > macro_ema)
short_regime = not use_ema_filter or (close < macro_ema)

long_condition  = bull_flip and long_regime and volat_pass and sqz_long_pass and smc_long_pass and rsi_long_pass and adx_pass and vol_pass
short_condition = bear_flip and short_regime and volat_pass and sqz_short_pass and smc_short_pass and rsi_short_pass and adx_pass and vol_pass

hasOpenTrade = strategy.opentrades > 0
entry_price = hasOpenTrade ? strategy.opentrades.entry_price(strategy.opentrades - 1) : na

// ==========================================
// 4. HYBRID TP / SL LEVELS
// ==========================================
calc_tp(is_long, base_price) =>
    float tp_p = na
    if not na(base_price)
        fixed_p = is_long ? base_price * (1 + tp_fixed_pct * 0.01) : base_price * (1 - tp_fixed_pct * 0.01)
        atr_p   = is_long ? base_price + (tp_atr_mult * atr_val)   : base_price - (tp_atr_mult * atr_val)
        if tp_mode == "Fixed"
            tp_p := fixed_p
        else if tp_mode == "ATR"
            tp_p := atr_p
        else if tp_mode == "Both"
            tp_p := is_long ? math.max(fixed_p, atr_p) : math.min(fixed_p, atr_p)
    tp_p

calc_sl(is_long, base_price) =>
    float sl_p = na
    if not na(base_price)
        fixed_p = is_long ? base_price * (1 - sl_fixed_pct * 0.01) : base_price * (1 + sl_fixed_pct * 0.01)
        atr_p   = is_long ? base_price - (sl_atr_mult * atr_val)   : base_price + (sl_atr_mult * atr_val)
        if sl_mode == "Fixed"
            sl_p := fixed_p
        else if sl_mode == "ATR"
            sl_p := atr_p
        else if sl_mode == "Both"
            sl_p := is_long ? math.max(fixed_p, atr_p) : math.min(fixed_p, atr_p)
    sl_p

tp_long_level  = calc_tp(true, entry_price)
sl_long_level  = calc_sl(true, entry_price)
tp_short_level = calc_tp(false, entry_price)
sl_short_level = calc_sl(false, entry_price)

// ==========================================
// 5. EXECUTION & ORDER MANAGEMENT
// ==========================================
var int bars_in_trade = 0
if strategy.position_size != 0
    bars_in_trade := bars_in_trade + 1
else
    bars_in_trade := 0

if long_condition
    strategy.entry("Long", strategy.long, comment="ST_Bull_Entry")
    bars_in_trade := 0

if short_condition
    strategy.entry("Short", strategy.short, comment="ST_Bear_Entry")
    bars_in_trade := 0

if strategy.position_size > 0
    strategy.exit("Exit_Long", "Long", limit=tp_long_level, stop=sl_long_level, comment="TP/SL_Long")

if strategy.position_size < 0
    strategy.exit("Exit_Short", "Short", limit=tp_short_level, stop=sl_short_level, comment="TP/SL_Short")

if (strategy.position_size > 0) and bear_flip
    strategy.close("Long", comment="ST_Bear_Flip_Exit")

if (strategy.position_size < 0) and bull_flip
    strategy.close("Short", comment="ST_Bull_Flip_Exit")

if use_tr_exit and (strategy.position_size > 0) and ta.crossunder(close, tr_ma)
    strategy.close("Long", comment="TR_MA_Exit_Long")

if use_tr_exit and (strategy.position_size < 0) and ta.crossover(close, tr_ma)
    strategy.close("Short", comment="TR_MA_Exit_Short")

if use_time_exit and (bars_in_trade >= max_bars_hold)
    if strategy.position_size > 0
        strategy.close("Long", comment="Time_Expiry_Long")
    if strategy.position_size < 0
        strategy.close("Short", comment="Time_Expiry_Short")

// ==========================================
// 6. VISUALIZATION
// ==========================================
plot(use_ema_filter ? macro_ema : na, "Macro EMA", color=color.new(color.orange, 20), linewidth=2)
plot(use_tr_exit ? tr_ma : na, "TR MA", color=color.new(color.purple, 30), linewidth=2)
plot(st_line, "SuperTrend", color=(st_dir == -1 ? color.green : color.red), linewidth=2)
bgcolor(st_dir == -1 ? color.new(color.green, 93) : color.new(color.red, 93), title="Regime Background")
'''
    return code

def _worker_simulate(task_args):
    """멀티프로세싱 워커 개별 실행 단위"""
    df, cand = task_args
    sim_res = run_simulation(df, cand, split_ratio=0.70)
    
    oos_sh = sim_res['oos']['sharpe']
    oos_mdd = abs(sim_res['oos']['mdd'])
    ratio = sim_res['overfitting_ratio']
    trades = sim_res['oos']['trades_count']
    
    score = oos_sh * 2.0 - (oos_mdd * 0.05) + (min(ratio, 2.0) * 0.5)
    if trades < 20: score -= 2.0
    
    return {
        'score': score,
        'params': cand,
        'sim_res': sim_res
    }

def run_ai_evolution_search(df, symbol="BTC/USDT", timeframe="1h", max_iterations=20, num_workers=None, progress_callback=None):
    """
    [멀티코어 병렬 가속 엔진]
    서버의 CPU 코어 수(num_workers)를 자동 감지하여 모든 코어에 병렬로 분산 연산 수행
    """
    total_cores = os.cpu_count() or 1
    if num_workers is None or num_workers <= 0:
        num_workers = min(max(total_cores, 1), 16)
        
    candidates = []
    # SuperTrend, Squeeze, SMC, RSI, ADX, Volume MA 조합 다차원 탐색
    for st_p in [5, 7, 10]:
        for st_m in [2.0, 3.0]:
            for use_sqz in [False, True]:
                for use_smc in [False, True]:
                    for use_rsi in [False, True]:
                        for use_adx in [False, True]:
                            for use_vol in [False, True]:
                                candidates.append({
                                    'st_period': st_p,
                                    'st_mult': st_m,
                                    'ema_len': 200,
                                    'use_ema_filter': True,
                                    'min_width_pct': 1.0,
                                    'use_min_volat': True,
                                    'use_squeeze': use_sqz,
                                    'sqz_len': 20,
                                    'bb_mult': 2.0,
                                    'kc_mult': 1.5,
                                    'use_smc': use_smc,
                                    'smc_swing_len': 5,
                                    'smc_mode': 'Structure',
                                    'use_rsi': use_rsi,
                                    'rsi_len': 14,
                                    'rsi_mode': 'Boundary',
                                    'rsi_ob': 70.0,
                                    'rsi_os': 30.0,
                                    'use_adx': use_adx,
                                    'adx_len': 14,
                                    'adx_threshold': 20.0,
                                    'use_vol': use_vol,
                                    'vol_ma_len': 20,
                                    'vol_mult': 1.0,
                                    'use_tr_exit': True,
                                    'tr_ma_len': 100,
                                    'tp_mode': 'ATR',
                                    'sl_mode': 'ATR',
                                    'tp_fixed_pct': 3.0,
                                    'sl_fixed_pct': 2.0,
                                    'tp_atr_mult': 3.5,
                                    'sl_atr_mult': 2.0,
                                    'use_time_exit': True,
                                    'max_bars_hold': 72
                                })
                    
    selected_candidates = candidates[:max_iterations]
    eval_results = []
    total_tasks = len(selected_candidates)
    
    start_t = time.time()
    
    if num_workers > 1:
        tasks = [(df, c) for c in selected_candidates]
        completed = 0
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_cand = {executor.submit(_worker_simulate, t): t for t in tasks}
            for future in as_completed(future_to_cand):
                res = future.result()
                eval_results.append(res)
                completed += 1
                if progress_callback:
                    pct = int(completed / total_tasks * 100)
                    elapsed = time.time() - start_t
                    progress_callback(pct, f"⚡ [{num_workers}개 CPU 코어 풀가동] 진화 세대 {completed}/{total_tasks} 병렬 연산 중 ({elapsed:.1f}초)")
    else:
        for idx, cand in enumerate(selected_candidates):
            res = _worker_simulate((df, cand))
            eval_results.append(res)
            if progress_callback:
                pct = int((idx + 1) / total_tasks * 100)
                progress_callback(pct, f"진화 세대 {idx+1}/{total_tasks} 검증 중...")

    elapsed_time = round(time.time() - start_t, 2)
    
    # 최고 성과 모델 선별
    eval_results.sort(key=lambda x: x['score'], reverse=True)
    best = eval_results[0]
    best_params = best['params']
    best_sim = best['sim_res']
    
    summary = {
        'symbol': symbol,
        'timeframe': timeframe,
        'oos_sharpe': best_sim['oos']['sharpe'],
        'oos_return': best_sim['oos']['return_pct'],
        'oos_mdd': best_sim['oos']['mdd'],
        'oos_win_rate': best_sim['oos']['win_rate'],
        'is_sharpe': best_sim['is']['sharpe'],
        'overfitting_ratio': best_sim['overfitting_ratio'],
        'workers_used': num_workers,
        'elapsed_time_sec': elapsed_time
    }
    
    clean_sym = symbol.replace("/", "")
    strategy_name = f"AI Auto-Evolved {clean_sym} {timeframe} Strategy v6"
    generated_pine = generate_pine_script_v6(strategy_name, best_params, summary)
    
    return {
        'best_params': best_params,
        'best_sim': best_sim,
        'summary': summary,
        'pine_code': generated_pine,
        'total_evaluated': total_tasks,
        'workers_used': num_workers,
        'elapsed_time_sec': elapsed_time
    }
