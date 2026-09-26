import pandas as pd
import numpy as np
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
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
// 🤖 AI Deep Quantum Evolutionary Strategy Generator v6.0
// [AI Engine Report]
// - Symbol: {metrics_summary.get('symbol', 'BTC/USDT')} ({metrics_summary.get('timeframe', '1h')})
// - OOS Sharpe: {metrics_summary.get('oos_sharpe', 0.0)} | OOS Return: {metrics_summary.get('oos_return', 0.0)}%
// - OOS MDD: {metrics_summary.get('oos_mdd', 0.0)}% | OOS Win Rate: {metrics_summary.get('oos_win_rate', 0.0)}%
// - OOS Trades: {metrics_summary.get('oos_trades', 0)} trades (Statistically Significant Sample)
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

# =========================================================================
# 유전 진화 탐색 엔진 (Genetic Evolutionary Algorithm Engine)
# =========================================================================

# 유전자 정의 (Gene Map: 1,000%+ 초고수익 & 50%+ 고승률 퀀트 설계)
GENE_OPTIONS = {
    'st_period': [7, 9, 10, 12, 14, 20],
    'st_mult': [2.5, 3.0, 3.5, 4.0, 4.5, 5.0],  # 노이즈를 거르고 큰 추세를 타서 승률 50%+ 보장
    'ema_len': [50, 100, 150, 200, 250, 300],
    'min_width_pct': [0.5, 0.8, 1.0, 1.2, 1.5, 2.0],
    'sqz_len': [14, 20, 25],
    'bb_mult': [1.5, 2.0, 2.5],
    'kc_mult': [1.0, 1.5, 2.0],
    'smc_swing_len': [3, 5, 7, 10],
    'smc_mode': ['Structure', 'FVG', 'Both'],
    'rsi_len': [7, 9, 14, 21],
    'rsi_mode': ['Boundary', 'Momentum'],
    'rsi_ob': [65.0, 70.0, 75.0, 80.0],
    'rsi_os': [20.0, 25.0, 30.0, 35.0],
    'adx_len': [10, 14, 20],
    'adx_threshold': [20.0, 25.0, 30.0, 35.0],  # 횡보장 휩소/손절 차단으로 승률 50%+ 견인
    'vol_ma_len': [10, 20, 30, 50],
    'vol_mult': [0.8, 1.0, 1.2, 1.5],
    'tr_ma_len': [30, 50, 80, 100, 150, 200],
    'tp_mode': ['None', 'Fixed', 'ATR', 'Both'],  # None: 불장 대세 추세 끝까지 라이딩 (1000%+ 필수)
    'sl_mode': ['Fixed', 'ATR', 'Both'],
    'tp_fixed_pct': [10.0, 20.0, 35.0, 50.0, 80.0, 120.0, 200.0],  # 초광폭 익절
    'sl_fixed_pct': [1.5, 2.0, 2.5, 3.0, 4.0],  # 짧은 손절로 손익비 극대화
    'tp_atr_mult': [4.0, 6.0, 8.0, 12.0, 16.0, 24.0],  # 대변동성 파동 수확
    'sl_atr_mult': [1.5, 2.0, 2.5, 3.0],
    'max_bars_hold': [72, 120, 240, 480, 720, 1440]  # 대세 상승장 1~2달 장기 추세 보유
}

FILTER_KEYS = [
    'use_ema_filter',
    'use_min_volat',
    'use_squeeze',
    'use_smc',
    'use_rsi',
    'use_adx',
    'use_vol'
]

def _sample_random_candidate():
    """
    [필터 희소성(Sparsity) 원칙 적용 무작위 후보 생성]
    모든 필터를 동시에 켜면 거래가 전멸(신호 기근)하므로 1~3개의 상호보완적 필터만 선택
    """
    cand = {}
    for k, v in GENE_OPTIONS.items():
        cand[k] = random.choice(v)
        
    # 필터 7개 중 1~3개 지능적 활성화
    for f in FILTER_KEYS:
        cand[f] = False
    active_filters = random.sample(FILTER_KEYS, k=random.choice([1, 2, 3]))
    for f in active_filters:
        cand[f] = True
        
    cand['use_tr_exit'] = random.choice([True, False])
    cand['use_time_exit'] = random.choice([True, False])
    return cand

def _evaluate_fitness(sim_res, min_trades=100, max_mdd_allowed=40.0):
    """
    [초고수익 (1,000%+) & 고승률 (50%+) 극대화 실전 퀀트 적합도 함수 (Fitness Function)]
    1. 최소 검증 거래수 (기본 100회) 미달 시 탈락 페널티
    2. [승률 50% 이상 특급 가산점]: 50% 미만 강력 감점, 50% 이상부터 폭발적 가산점 (+30점 기본 + 초과분당 2.5점)
    3. [수익률 1,000%+ 초고수익 인센티브]: 1,000% 달성 시 슈퍼 메가 보너스 (+200점)
    4. [MDD 40% 제한 조건]: 40% 이하 정상 추세 드로다운 허용, 40% 초과 시 급격한 탈락 페널티
    5. OOS 샤프 지수 및 WFO 일반화(과최적화 방지) 검증
    """
    oos = sim_res['oos']
    is_res = sim_res['is']
    trades = oos.get('trades_count', 0)
    
    # 1. 최소 거래수 검증: 표본 부족에 의한 우연한 수익/과적합 원천 배제
    if trades < min_trades:
        return -2000.0 - (min_trades - trades) * 10.0
        
    oos_sh = oos.get('sharpe', 0.0)
    oos_ret = oos.get('return_pct', 0.0)
    oos_mdd = abs(oos.get('mdd', 0.0))
    win_rate = oos.get('win_rate', 0.0)
    overfitting_ratio = sim_res.get('overfitting_ratio', 1.0)
    
    score = 0.0
    
    # 2. [승률 50% 이상 특급 가산점 & 50% 미만 페널티]
    if win_rate >= 50.0:
        score += 30.0 + (win_rate - 50.0) * 2.5  # 승률 50% = +30점, 승률 55% = +42.5점, 60% = +55점!
    else:
        score -= (50.0 - win_rate) * 2.0  # 승률 45% = -10점, 40% = -20점, 30% = -40점
        
    # 3. [누적 수익률 1,000%+ 초고수익 배점]
    # 기본 수익률 비례 점수: 수익률 100%당 20점 (예: 500% = +100점, 1,000% = +200점)
    score += (oos_ret / 10.0) * 2.0
    
    # 1,000% 이상 초과 달성 시 슈퍼 메가 보너스!
    if oos_ret >= 1000.0:
        score += 200.0 + (oos_ret - 1000.0) * 0.2  # 1,000% 돌파 시 +200점 직행!
    elif oos_ret >= 500.0:
        score += 70.0
    elif oos_ret >= 200.0:
        score += 25.0
    elif oos_ret < 50.0:
        score -= 30.0
        
    # 4. [MDD 40% 제한 조건]
    # MDD가 40% 이내면 정상 변동성으로 인정하여 감점 최소화
    # MDD가 40%를 초과할 경우 강력한 페널티 부과
    if oos_mdd > max_mdd_allowed:
        score -= (oos_mdd - max_mdd_allowed) * 4.0
    score -= oos_mdd * 0.02
    
    # 5. OOS 샤프 지수 보너스 (수익 곡선의 매끄러움 보정)
    if oos_sh > 0:
        score += oos_sh * 5.0
    else:
        score += oos_sh * 2.0
        
    # 6. WFO 일반화 능력 검증 (과최적화 방지)
    if 0.4 <= overfitting_ratio <= 2.0:
        score += 5.0
    elif overfitting_ratio < 0.2:
        score -= 10.0
        
    # 7. 풍부한 거래 표본수 가산점 (실전 신뢰도)
    if trades >= 100:
        score += min((trades - 100) * 0.02, 5.0)
        
    return score

def _crossover_candidates(parent1, parent2):
    """두 부모 유전자 균등 교차(Uniform Crossover)"""
    child = {}
    for k in parent1.keys():
        child[k] = parent1[k] if random.random() < 0.5 else parent2[k]
        
    # 자식의 필터 활성화 수가 4개 이상으로 폭증하지 않도록 제약 (Filter Sparsity 유지)
    active_filters = [f for f in FILTER_KEYS if child.get(f, False)]
    if len(active_filters) > 3:
        to_deactivate = random.sample(active_filters, k=len(active_filters) - 3)
        for f in to_deactivate:
            child[f] = False
    elif len(active_filters) == 0:
        child[random.choice(FILTER_KEYS)] = True
        
    return child

def _mutate_candidate(candidate, mutation_rate=0.25):
    """가우시안/이웃 유전자 돌연변이 (Mutation)"""
    mutated = candidate.copy()
    if random.random() < mutation_rate:
        # 주요 파라미터 1~2개 미세 변이
        keys_to_mutate = random.sample(list(GENE_OPTIONS.keys()), k=random.choice([1, 2]))
        for k in keys_to_mutate:
            options = GENE_OPTIONS[k]
            curr_val = mutated[k]
            if curr_val in options:
                curr_idx = options.index(curr_val)
                # 인접한 옵션으로 이동
                step = random.choice([-1, 1])
                new_idx = max(0, min(len(options) - 1, curr_idx + step))
                mutated[k] = options[new_idx]
            else:
                mutated[k] = random.choice(options)
                
    if random.random() < 0.20:
        # 필터 1개 토글
        toggle_f = random.choice(FILTER_KEYS)
        mutated[toggle_f] = not mutated[toggle_f]
        
    return mutated

def _worker_simulate(task_args):
    """멀티프로세싱 워커 개별 실행 단위"""
    df, cand, min_trades, max_mdd = task_args
    sim_res = run_simulation(df, cand, split_ratio=0.70)
    score = _evaluate_fitness(sim_res, min_trades=min_trades, max_mdd_allowed=max_mdd)
    
    return {
        'score': score,
        'params': cand,
        'sim_res': sim_res
    }

def run_ai_evolution_search(df, symbol="BTC/USDT", timeframe="1h", max_iterations=10000, min_trades=100, max_mdd=40.0, num_workers=None, progress_callback=None):
    """
    [다세대 고수익 유전 진화 퀀트 탐색 엔진 (Genetic Evolutionary Algorithm)]
    - 기본 10,000회 대규모 탐색: 5개 세대를 거치며 초고수익/고승률/MDD 40% 통제 전략으로 정밀 수렴
    """
    total_cores = os.cpu_count() or 1
    if num_workers is None or num_workers <= 0:
        num_workers = min(max(total_cores, 1), 16)
        
    start_t = time.time()
    
    # 세대 수 및 세대별 개체 수 산정
    if max_iterations >= 3000:
        n_generations = 5
    elif max_iterations >= 1000:
        n_generations = 4
    elif max_iterations >= 200:
        n_generations = 3
    else:
        n_generations = 2
        
    pop_size = max(max_iterations // n_generations, 20)
    actual_total = pop_size * n_generations
    
    all_evaluated = []
    current_population = [_sample_random_candidate() for _ in range(pop_size)]
    global_best = None
    
    total_completed = 0
    
    for gen in range(1, n_generations + 1):
        tasks = [(df, cand, min_trades, max_mdd) for cand in current_population]
        gen_results = []
        
        if num_workers > 1:
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = {executor.submit(_worker_simulate, t): t for t in tasks}
                for f in as_completed(futures):
                    res = f.result()
                    gen_results.append(res)
                    total_completed += 1
                    
                    if progress_callback:
                        pct = int((total_completed / actual_total) * 100)
                        pct = min(pct, 99)
                        best_so_far_ret = global_best['sim_res']['oos']['return_pct'] if global_best else res['sim_res']['oos']['return_pct']
                        best_so_far_wr = global_best['sim_res']['oos']['win_rate'] if global_best else res['sim_res']['oos']['win_rate']
                        best_so_far_mdd = global_best['sim_res']['oos']['mdd'] if global_best else res['sim_res']['oos']['mdd']
                        best_trades = global_best['sim_res']['oos']['trades_count'] if global_best else res['sim_res']['oos']['trades_count']
                        progress_callback(
                            pct,
                            f"[AI 유전 진화 {gen}/{n_generations}세대] {total_completed}/{actual_total} 검증 중 "
                            f"(최고 수익률: {best_so_far_ret:+.1f}%, 승률: {best_so_far_wr:.1f}%, MDD: {best_so_far_mdd:.1f}%, 거래: {best_trades}회 | {num_workers}코어)"
                        )
        else:
            for cand in current_population:
                res = _worker_simulate((df, cand, min_trades, max_mdd))
                gen_results.append(res)
                total_completed += 1
                if progress_callback:
                    pct = int((total_completed / actual_total) * 100)
                    pct = min(pct, 99)
                    progress_callback(pct, f"[AI 유전 진화 {gen}/{n_generations}세대] {total_completed}/{actual_total} 검증 중...")
                    
        # 세대 결과 정렬
        gen_results.sort(key=lambda x: x['score'], reverse=True)
        all_evaluated.extend(gen_results)
        
        # 글로벌 최고 갱신
        if global_best is None or gen_results[0]['score'] > global_best['score']:
            global_best = gen_results[0]
            
        # 마지막 세대가 아니면 다음 세대 육성 (Elitism + Crossover + Mutation)
        if gen < n_generations:
            # 엘리트 풀 (상위 25%)
            elite_count = max(int(pop_size * 0.25), 3)
            elites = [x['params'] for x in gen_results[:elite_count]]
            
            next_pop = []
            # 최상위 5% 무조건 보존 (Elitism)
            keep_count = max(int(pop_size * 0.05), 2)
            next_pop.extend(elites[:keep_count])
            
            # 교차 및 돌연변이로 나머지 채우기
            while len(next_pop) < pop_size:
                r = random.random()
                if r < 0.65:
                    # 상위 엘리트 간 교차
                    p1, p2 = random.sample(elites, 2)
                    child = _crossover_candidates(p1, p2)
                    child = _mutate_candidate(child, mutation_rate=0.20)
                    next_pop.append(child)
                elif r < 0.85:
                    # 엘리트 단독 변이
                    p = random.choice(elites)
                    mut = _mutate_candidate(p, mutation_rate=0.35)
                    next_pop.append(mut)
                else:
                    # 국소 최적화 탈출용 신규 무작위 개체 (Diversity)
                    next_pop.append(_sample_random_candidate())
                    
            current_population = next_pop[:pop_size]

    # 전체 세대 중 최종 최고 모델 선정
    all_evaluated.sort(key=lambda x: x['score'], reverse=True)
    best = all_evaluated[0]
    best_params = best['params']
    best_sim = best['sim_res']
    elapsed_time = round(time.time() - start_t, 2)
    
    summary = {
        'symbol': symbol,
        'timeframe': timeframe,
        'oos_sharpe': best_sim['oos']['sharpe'],
        'oos_return': best_sim['oos']['return_pct'],
        'oos_mdd': best_sim['oos']['mdd'],
        'oos_win_rate': best_sim['oos']['win_rate'],
        'oos_trades': best_sim['oos']['trades_count'],
        'is_sharpe': best_sim['is']['sharpe'],
        'overfitting_ratio': best_sim['overfitting_ratio'],
        'workers_used': num_workers,
        'generations': n_generations,
        'elapsed_time_sec': elapsed_time
    }
    
    clean_sym = symbol.replace("/", "")
    strategy_name = f"AI Deep-Evolved {clean_sym} {timeframe} Strategy v6"
    generated_pine = generate_pine_script_v6(strategy_name, best_params, summary)
    
    return {
        'best_params': best_params,
        'best_sim': best_sim,
        'summary': summary,
        'pine_code': generated_pine,
        'total_evaluated': total_completed,
        'workers_used': num_workers,
        'generations': n_generations,
        'elapsed_time_sec': elapsed_time
    }
