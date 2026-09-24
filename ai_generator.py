import pandas as pd
import numpy as np
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from quant_engine import run_simulation

def generate_pine_script_v6(strategy_title, params, metrics_summary):
    """
    최적화된 파라미터와 메트릭을 바탕으로 공식 Pine Script v6 완전한 코드를 동적 합성
    """
    st_period = params.get('st_period', 7)
    st_mult = params.get('st_mult', 3.0)
    use_ema = params.get('use_ema_filter', True)
    ema_len = params.get('ema_len', 200)
    use_min_volat = params.get('use_min_volat', True)
    min_width = params.get('min_width_pct', 1.5)
    use_tr = params.get('use_tr_exit', True)
    tr_len = params.get('tr_ma_len', 100)
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

group_trma = "3. Trend Reversal MA (TR MA Emergency Exit)"
use_tr_exit  = input.bool({str(use_tr).lower()}, "Enable TR MA Exit", group=group_trma)
tr_ma_type   = input.string("EMA", "TR MA Type", options=["SMA", "EMA", "RMA", "WMA"], group=group_trma)
tr_ma_len    = input.int({tr_len}, "TR MA Length", minval=10, group=group_trma)

group_tpsl = "4. Hybrid Take Profit & Stop Loss"
tp_mode      = input.string("{tp_mode}", "TP Price Mode", options=["None", "Fixed", "ATR", "Both"], group=group_tpsl)
sl_mode      = input.string("{sl_mode}", "SL Price Mode", options=["None", "Fixed", "ATR", "Both"], group=group_tpsl)
tp_fixed_pct = input.float({tp_fixed}, "Fixed Take Profit (%)", minval=0.1, step=0.1, group=group_tpsl)
sl_fixed_pct = input.float({sl_fixed}, "Fixed Stop Loss (%)", minval=0.1, step=0.1, group=group_tpsl)
tp_atr_mult  = input.float({tp_atr}, "TP ATR Multiplier", minval=0.5, step=0.1, group=group_tpsl)
sl_atr_mult  = input.float({sl_atr}, "SL ATR Multiplier", minval=0.5, step=0.1, group=group_tpsl)

group_time = "5. Time Expiry Exit"
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

// ==========================================
// 3. REGIME & TRIGGER LOGIC
// ==========================================
bull_flip = (st_dir == -1) and (st_dir[1] == 1)
bear_flip = (st_dir == 1) and (st_dir[1] == -1)

long_regime  = not use_ema_filter or (close > macro_ema)
short_regime = not use_ema_filter or (close < macro_ema)

long_condition  = bull_flip and long_regime and volat_pass
short_condition = bear_flip and short_regime and volat_pass

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
        # 가용 코어 수에 맞게 자동 지정 (최대 16)
        num_workers = min(max(total_cores, 1), 16)
        
    candidates = []
    for st_p in [5, 7, 9, 10, 12, 14]:
        for st_m in [2.0, 2.5, 3.0, 3.5, 4.0]:
            for use_tr in [True, False]:
                for tp_m in ['ATR', 'Fixed', 'Both']:
                    candidates.append({
                        'st_period': st_p,
                        'st_mult': st_m,
                        'ema_len': 200,
                        'use_ema_filter': True,
                        'min_width_pct': 1.5,
                        'use_min_volat': True,
                        'use_tr_exit': use_tr,
                        'tr_ma_len': 100,
                        'tp_mode': tp_m,
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
    
    # 🚀 멀티코어 병렬 분산 처리 (ProcessPoolExecutor)
    # 단일 코어 환경에서는 오버헤드를 피하기 위해 직렬 실행, 멀티코어에서는 병렬 가속
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
        # 단일 코어 순차 실행
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
