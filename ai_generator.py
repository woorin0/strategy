import numpy as np
from quant_engine import run_simulation

# =========================================================================
# 전략 아키텍처 정의 (Strategy Archetypes Definition)
# =========================================================================
STRATEGY_ARCHETYPES = {
    'SuperTrend_Trend': {
        'name_kr': 'SuperTrend 추세추종 & 변동성 돌파',
        'icon': '🚀',
        'desc': 'SuperTrend 강세 전환 시 매수하고 약세 전환 시 매도 현금화하는 현물 롱 추세 알파 전략'
    },
    'EMA_Cross': {
        'name_kr': 'Dual EMA 모멘텀 크로스오버 돌파',
        'icon': '📈',
        'desc': '단기 및 장기 지수이동평균선의 골든크로스 시 매수하고 데드크로스 시 매도 현금화하는 현물 롱 전략'
    },
    'Squeeze_Breakout': {
        'name_kr': 'Squeeze Momentum 변동성 수축-폭발 돌파',
        'icon': '⚡',
        'desc': '볼린저 밴드가 켈트너 채널 안으로 압축된 후 상방 모멘텀 0선 분출 시 매수하는 현물 롱 전략'
    },
    'SMC_Structure': {
        'name_kr': 'Smart Money Concepts (BOS 구조 갱신) 기관 돌파',
        'icon': '🏛️',
        'desc': '스마트 머니의 이전 스윙 고점 돌파(Bullish BOS) 및 수급 불균형(FVG)을 포착하여 매수하는 기관 추종 현물 전략'
    },
    'RSI_Reversal': {
        'name_kr': 'RSI 과매수/과매도 스윙 평균회귀 역발상',
        'icon': '🎯',
        'desc': '극단적 과매도(침체) 구간 이탈 후 반등하는 파동을 포착하여 저점 매수하는 현물 스윙 전략'
    }
}

STRATEGY_TYPE_KEYS = list(STRATEGY_ARCHETYPES.keys())

def generate_pine_script_v6(strategy_title, params, metrics_summary):
    """
    [모듈형 동적 파인스크립트 v6 합성기 (Modular Pine Script v6 Synthesizer)]
    선택된 전략 아키텍처(SuperTrend, EMA Cross, Squeeze, SMC, RSI) 및
    실제 활성화된 보조 필터들만을 정밀하게 추출하여, 완전히 독립적이고
    군더더기 없는 최상급 Pine Script v6 공식 코드를 동적으로 합성합니다.
    """
    strat_type = params.get('strategy_type', 'SuperTrend_Trend')
    meta = STRATEGY_ARCHETYPES.get(strat_type, STRATEGY_ARCHETYPES['SuperTrend_Trend'])
    type_name_kr = meta['name_kr']
    type_icon = meta['icon']
    type_desc = meta['desc']
    
    # 1. 공통 청산 및 리스크 관리 파라미터
    tp_mode = params.get('tp_mode', 'ATR')
    sl_mode = params.get('sl_mode', 'ATR')
    tp_fixed = float(params.get('tp_fixed_pct', 3.0))
    sl_fixed = float(params.get('sl_fixed_pct', 2.0))
    tp_atr = float(params.get('tp_atr_mult', 3.5))
    sl_atr = float(params.get('sl_atr_mult', 2.0))
    use_tr = bool(params.get('use_tr_exit', True))
    tr_len = int(params.get('tr_ma_len', 100))
    use_time = bool(params.get('use_time_exit', True))
    max_bars = int(params.get('max_bars_hold', 72))
    
    # 2. 보조 필터 사용 여부 (Sparsity)
    use_ema = bool(params.get('use_ema_filter', False)) and (strat_type != 'EMA_Cross')
    ema_len = int(params.get('ema_len', 200))
    use_min_volat = bool(params.get('use_min_volat', False))
    min_width = float(params.get('min_width_pct', 1.5))
    use_adx = bool(params.get('use_adx', False))
    adx_len = int(params.get('adx_len', 14))
    adx_threshold = float(params.get('adx_threshold', 20.0))
    use_vol = bool(params.get('use_vol', False))
    vol_len = int(params.get('vol_ma_len', 20))
    vol_mult = float(params.get('vol_mult', 1.0))
    
    use_sqz_as_filter = bool(params.get('use_squeeze', False)) and (strat_type != 'Squeeze_Breakout')
    sqz_len = int(params.get('sqz_len', 20))
    bb_mult = float(params.get('bb_mult', 2.0))
    kc_mult = float(params.get('kc_mult', 1.5))
    
    use_smc_as_filter = bool(params.get('use_smc', False)) and (strat_type != 'SMC_Structure')
    smc_swing = int(params.get('smc_swing_len', 5))
    smc_mode = params.get('smc_mode', 'Structure')
    
    use_rsi_as_filter = bool(params.get('use_rsi', False)) and (strat_type != 'RSI_Reversal')
    rsi_len = int(params.get('rsi_len', 14))
    rsi_mode = params.get('rsi_mode', 'Boundary')
    rsi_ob = float(params.get('rsi_ob', 70.0))
    rsi_os = float(params.get('rsi_os', 30.0))

    # 코드 버퍼 조립 시작
    sections = []
    
    # [헤더 섹션]
    sections.append(f'''//@version=6
// =========================================================================
// AI Deep Quantum Evolutionary Strategy Generator v6.0
// [전략 아키텍처]: {type_icon} {type_name_kr} ({strat_type})
// [거래 모드]: 🪙 현물 롱 전용 매매 (Spot Long-Only)
// [전략 원리]: {type_desc}
// -------------------------------------------------------------------------
// [AI Engine 백테스트 성과 리포트]
// - 대상 심볼: {metrics_summary.get('symbol', 'BTC/USDT')} ({metrics_summary.get('timeframe', '1h')})
// - OOS 샤프 지수: {metrics_summary.get('oos_sharpe', 0.0)} | OOS 누적 수익률: {metrics_summary.get('oos_return', 0.0)}%
// - OOS 최대 낙폭(MDD): {metrics_summary.get('oos_mdd', 0.0)}% | OOS 승률: {metrics_summary.get('oos_win_rate', 0.0)}%
// - OOS 거래 횟수: {metrics_summary.get('oos_trades', 0)}회 (과최적화 배제 표본)
// =========================================================================
strategy("{strategy_title}", 
         overlay=true, 
         initial_capital=10000, 
         default_qty_type=strategy.percent_of_equity, 
         default_qty_value=100, 
         commission_type=strategy.commission.percent, 
         commission_value=0.08, 
         process_orders_on_close=true)
''')

    # [1. 입력 파라미터 섹션 - 전략 유형별 고유 파라미터만 노출]
    input_lines = ["// ==========================================", "// 1. INPUT PARAMETERS (AI 최적화 입력 변수)", "// =========================================="]
    
    if strat_type == 'SuperTrend_Trend':
        st_period = int(params.get('st_period', 7))
        st_mult = float(params.get('st_mult', 3.0))
        input_lines.append('group_core = "1. SuperTrend 추세 코어 엔진"')
        input_lines.append(f'st_period = input.int({st_period}, "SuperTrend ATR 주기", minval=1, group=group_core)')
        input_lines.append(f'st_mult   = input.float({st_mult}, "SuperTrend 승수 (Multiplier)", minval=0.1, step=0.1, group=group_core)')
    elif strat_type == 'EMA_Cross':
        ema_fast = max(int(ema_len // 4), 10)
        input_lines.append('group_core = "1. Dual EMA 크로스 코어 엔진"')
        input_lines.append(f'ema_fast_len = input.int({ema_fast}, "단기 EMA 주기 (Fast)", minval=5, group=group_core)')
        input_lines.append(f'ema_slow_len = input.int({ema_len}, "장기 EMA 주기 (Slow/Macro)", minval=20, group=group_core)')
    elif strat_type == 'Squeeze_Breakout':
        input_lines.append('group_core = "1. Squeeze Momentum 변동성 수축/폭발 엔진"')
        input_lines.append(f'sqz_len = input.int({sqz_len}, "Squeeze 채널 주기", minval=5, group=group_core)')
        input_lines.append(f'bb_mult = input.float({bb_mult}, "BB 승수 (StdDev)", minval=0.5, step=0.1, group=group_core)')
        input_lines.append(f'kc_mult = input.float({kc_mult}, "KC 승수 (ATR)", minval=0.5, step=0.1, group=group_core)')
    elif strat_type == 'SMC_Structure':
        input_lines.append('group_core = "1. Smart Money Concepts (SMC) 기관 구조 엔진"')
        input_lines.append(f'smc_swing_len = input.int({smc_swing}, "SMC 스윙 피봇 길이 (Swing Pivot)", minval=2, group=group_core)')
        input_lines.append(f'smc_mode      = input.string("{smc_mode}", "SMC 진입 확인 모드", options=["Structure", "FVG", "Both"], group=group_core)')
    elif strat_type == 'RSI_Reversal':
        input_lines.append('group_core = "1. RSI 평균회귀 역발상 코어 엔진"')
        input_lines.append(f'rsi_len = input.int({rsi_len}, "RSI 주기", minval=2, group=group_core)')
        input_lines.append(f'rsi_ob  = input.float({rsi_ob}, "과매수 기준선 (OB)", minval=50.0, maxval=95.0, group=group_core)')
        input_lines.append(f'rsi_os  = input.float({rsi_os}, "과매도 기준선 (OS)", minval=5.0, maxval=50.0, group=group_core)')

    # 활성화된 보조 필터 입력단 추가
    filter_group_added = False
    def ensure_filter_group():
        nonlocal filter_group_added
        if not filter_group_added:
            input_lines.append('\ngroup_filter = "2. AI 선별 활성 보조 필터"')
            filter_group_added = True

    if use_ema:
        ensure_filter_group()
        input_lines.append(f'use_ema_filter = input.bool(true, "거시 추세 EMA 필터", group=group_filter)')
        input_lines.append(f'ema_len        = input.int({ema_len}, "거시 EMA 주기", minval=10, group=group_filter)')
        
    if use_min_volat:
        ensure_filter_group()
        input_lines.append(f'use_min_volat  = input.bool(true, "최소 캔들 변동폭 필터", group=group_filter)')
        input_lines.append(f'min_width_pct  = input.float({min_width}, "최소 변동폭 (%)", minval=0.1, step=0.1, group=group_filter)')
        
    if use_sqz_as_filter:
        ensure_filter_group()
        input_lines.append(f'use_squeeze = input.bool(true, "Squeeze Momentum 모멘텀 필터", group=group_filter)')
        input_lines.append(f'sqz_len     = input.int({sqz_len}, "Squeeze 주기", minval=5, group=group_filter)')
        
    if use_smc_as_filter:
        ensure_filter_group()
        input_lines.append(f'use_smc       = input.bool(true, "SMC 기관 구조 필터", group=group_filter)')
        input_lines.append(f'smc_swing_len = input.int({smc_swing}, "SMC 스윙 주기", minval=2, group=group_filter)')
        input_lines.append(f'smc_mode      = input.string("{smc_mode}", "SMC 모드", options=["Structure", "FVG", "Both"], group=group_filter)')
        
    if use_rsi_as_filter:
        ensure_filter_group()
        input_lines.append(f'use_rsi_filter = input.bool(true, "RSI 필터", group=group_filter)')
        input_lines.append(f'rsi_len        = input.int({rsi_len}, "RSI 주기", minval=2, group=group_filter)')
        input_lines.append(f'rsi_mode       = input.string("{rsi_mode}", "RSI 모드", options=["Boundary", "Momentum"], group=group_filter)')
        input_lines.append(f'rsi_ob         = input.float({rsi_ob}, "과매수 상한", group=group_filter)')
        input_lines.append(f'rsi_os         = input.float({rsi_os}, "과매도 하한", group=group_filter)')
        
    if use_adx:
        ensure_filter_group()
        input_lines.append(f'use_adx_filter = input.bool(true, "ADX 추세 강도 필터", group=group_filter)')
        input_lines.append(f'adx_len        = input.int({adx_len}, "ADX 주기", minval=5, group=group_filter)')
        input_lines.append(f'adx_threshold  = input.float({adx_threshold}, "최소 ADX 기준값", minval=5.0, group=group_filter)')
        
    if use_vol:
        ensure_filter_group()
        input_lines.append(f'use_vol_filter = input.bool(true, "거래량 수급 필터", group=group_filter)')
        input_lines.append(f'vol_ma_len     = input.int({vol_len}, "거래량 MA 주기", minval=5, group=group_filter)')
        input_lines.append(f'vol_mult       = input.float({vol_mult}, "거래량 돌파 배수", minval=0.5, step=0.1, group=group_filter)')

    # 청산 파라미터
    input_lines.append('\ngroup_exit = "3. 리스크 통제 & 청산 엔진"')
    input_lines.append(f'tp_mode      = input.string("{tp_mode}", "익절(TP) 모드", options=["None", "Fixed", "ATR", "Both"], group=group_exit)')
    input_lines.append(f'sl_mode      = input.string("{sl_mode}", "손절(SL) 모드", options=["None", "Fixed", "ATR", "Both"], group=group_exit)')
    input_lines.append(f'tp_fixed_pct = input.float({tp_fixed}, "고정 익절 목표 (%)", minval=0.1, step=0.1, group=group_exit)')
    input_lines.append(f'sl_fixed_pct = input.float({sl_fixed}, "고정 손절 제한 (%)", minval=0.1, step=0.1, group=group_exit)')
    input_lines.append(f'tp_atr_mult  = input.float({tp_atr}, "ATR 익절 승수", minval=0.5, step=0.1, group=group_exit)')
    input_lines.append(f'sl_atr_mult  = input.float({sl_atr}, "ATR 손절 승수", minval=0.5, step=0.1, group=group_exit)')
    
    if use_tr:
        input_lines.append(f'use_tr_exit  = input.bool(true, "TR MA 비상 청산 사용", group=group_exit)')
        input_lines.append(f'tr_ma_len    = input.int({tr_len}, "TR MA 주기", minval=10, group=group_exit)')
    else:
        input_lines.append('use_tr_exit  = false')
        
    if use_time:
        input_lines.append(f'use_time_exit = input.bool(true, "시간 만기 청산 사용", group=group_exit)')
        input_lines.append(f'max_bars_hold = input.int({max_bars}, "최대 보유 봉 수", minval=1, group=group_exit)')
    else:
        input_lines.append('use_time_exit = false')

    sections.append("\n".join(input_lines))

    # [2. 지표 계산 및 로직 섹션]
    calc_lines = ["\n// ==========================================", "// 2. INDICATORS & LOGIC SYNTHESIS", "// =========================================="]
    calc_lines.append("atr_val = ta.atr(14)")
    
    # 메인 전략 지표 계산
    if strat_type == 'SuperTrend_Trend':
        calc_lines.append("[st_line, st_dir] = ta.supertrend(st_mult, st_period)")
        calc_lines.append("trig_long  = (st_dir == -1) and (st_dir[1] == 1)")
        calc_lines.append("trig_short = (st_dir == 1) and (st_dir[1] == -1)")
    elif strat_type == 'EMA_Cross':
        calc_lines.append("fast_ema = ta.ema(close, ema_fast_len)")
        calc_lines.append("slow_ema = ta.ema(close, ema_slow_len)")
        calc_lines.append("trig_long  = ta.crossover(close, slow_ema)")
        calc_lines.append("trig_short = ta.crossunder(close, slow_ema)")
    elif strat_type == 'Squeeze_Breakout':
        calc_lines.append("bb_basis = ta.sma(close, sqz_len)")
        calc_lines.append("bb_dev = bb_mult * ta.stdev(close, sqz_len)")
        calc_lines.append("kc_tr = ta.rma(ta.tr, sqz_len)")
        calc_lines.append("sqz_val = ta.linreg(close - math.avg(math.avg(ta.highest(high, sqz_len), ta.lowest(low, sqz_len)), ta.sma(close, sqz_len)), sqz_len, 0)")
        calc_lines.append("trig_long  = ta.crossover(sqz_val, 0.0)")
        calc_lines.append("trig_short = ta.crossunder(sqz_val, 0.0)")
    elif strat_type == 'SMC_Structure':
        calc_lines.append("ph = ta.pivothigh(high, smc_swing_len, smc_swing_len)")
        calc_lines.append("pl = ta.pivotlow(low, smc_swing_len, smc_swing_len)")
        calc_lines.append("var float last_ph = na")
        calc_lines.append("var float last_pl = na")
        calc_lines.append("if not na(ph)")
        calc_lines.append("    last_ph := ph")
        calc_lines.append("if not na(pl)")
        calc_lines.append("    last_pl := pl")
        calc_lines.append("bull_bos = not na(last_ph) and ta.crossover(close, last_ph)")
        calc_lines.append("bear_bos = not na(last_pl) and ta.crossunder(close, last_pl)")
        calc_lines.append("bull_fvg = (low > high[2])")
        calc_lines.append("bear_fvg = (high < low[2])")
        calc_lines.append("recent_bull_fvg = bull_fvg or bull_fvg[1] or bull_fvg[2] or bull_fvg[3]")
        calc_lines.append("recent_bear_fvg = bear_fvg or bear_fvg[1] or bear_fvg[2] or bear_fvg[3]")
        calc_lines.append('trig_long  = smc_mode == "Structure" ? bull_bos : (smc_mode == "FVG" ? recent_bull_fvg : (bull_bos and recent_bull_fvg))')
        calc_lines.append('trig_short = smc_mode == "Structure" ? bear_bos : (smc_mode == "FVG" ? recent_bear_fvg : (bear_bos and recent_bear_fvg))')
    elif strat_type == 'RSI_Reversal':
        calc_lines.append("rsi_val = ta.rsi(close, rsi_len)")
        calc_lines.append("trig_long  = ta.crossover(rsi_val, rsi_os)")
        calc_lines.append("trig_short = ta.crossunder(rsi_val, rsi_ob)")

    # 보조 필터 계산 및 조건문
    filter_cond_long = []
    filter_cond_short = []
    
    if use_min_volat:
        calc_lines.append("volat_ma = ta.sma(((high - low) / math.max(close, syminfo.mintick)) * 100, 20)")
        calc_lines.append("volat_ok = not use_min_volat or (volat_ma >= min_width_pct)")
        filter_cond_long.append("volat_ok")
        filter_cond_short.append("volat_ok")
        
    if use_ema:
        calc_lines.append("macro_ema = ta.ema(close, ema_len)")
        calc_lines.append("ema_long_ok  = not use_ema_filter or (close > macro_ema)")
        calc_lines.append("ema_short_ok = not use_ema_filter or (close < macro_ema)")
        filter_cond_long.append("ema_long_ok")
        filter_cond_short.append("ema_short_ok")
        
    if use_sqz_as_filter:
        calc_lines.append("filter_sqz_val = ta.linreg(close - math.avg(math.avg(ta.highest(high, sqz_len), ta.lowest(low, sqz_len)), ta.sma(close, sqz_len)), sqz_len, 0)")
        calc_lines.append("sqz_long_ok  = not use_squeeze or (filter_sqz_val > 0)")
        calc_lines.append("sqz_short_ok = not use_squeeze or (filter_sqz_val < 0)")
        filter_cond_long.append("sqz_long_ok")
        filter_cond_short.append("sqz_short_ok")
        
    if use_smc_as_filter:
        calc_lines.append("f_ph = ta.pivothigh(high, smc_swing_len, smc_swing_len)")
        calc_lines.append("f_pl = ta.pivotlow(low, smc_swing_len, smc_swing_len)")
        calc_lines.append("var float f_last_ph = na")
        calc_lines.append("var float f_last_pl = na")
        calc_lines.append("if not na(f_ph)")
        calc_lines.append("    f_last_ph := f_ph")
        calc_lines.append("if not na(f_pl)")
        calc_lines.append("    f_last_pl := f_pl")
        calc_lines.append("f_bull_bos = not na(f_last_ph) and close > f_last_ph")
        calc_lines.append("f_bear_bos = not na(f_last_pl) and close < f_last_pl")
        calc_lines.append("smc_long_ok  = not use_smc or f_bull_bos")
        calc_lines.append("smc_short_ok = not use_smc or f_bear_bos")
        filter_cond_long.append("smc_long_ok")
        filter_cond_short.append("smc_short_ok")
        
    if use_rsi_as_filter:
        calc_lines.append("filter_rsi = ta.rsi(close, rsi_len)")
        calc_lines.append('rsi_long_ok  = not use_rsi_filter or (rsi_mode == "Boundary" ? (filter_rsi < rsi_ob) : (filter_rsi > 50.0))')
        calc_lines.append('rsi_short_ok = not use_rsi_filter or (rsi_mode == "Boundary" ? (filter_rsi > rsi_os) : (filter_rsi < 50.0))')
        filter_cond_long.append("rsi_long_ok")
        filter_cond_short.append("rsi_short_ok")
        
    if use_adx:
        calc_lines.append("[di_plus, di_minus, adx_val] = ta.dmi(adx_len, adx_len)")
        calc_lines.append("adx_ok = not use_adx_filter or (adx_val >= adx_threshold)")
        filter_cond_long.append("adx_ok")
        filter_cond_short.append("adx_ok")
        
    if use_vol:
        calc_lines.append("vol_ma = ta.sma(volume, vol_ma_len)")
        calc_lines.append("vol_ok = not use_vol_filter or (volume >= vol_ma * vol_mult)")
        filter_cond_long.append("vol_ok")
        filter_cond_short.append("vol_ok")
        
    if use_tr:
        calc_lines.append("tr_ma = ta.ema(close, tr_ma_len)")

    # 진입 조건문 결합
    l_cond_str = " and ".join(["trig_long"] + filter_cond_long)
    s_cond_str = " and ".join(["trig_short"] + filter_cond_short)
    calc_lines.append(f"\nlong_condition  = {l_cond_str}")
    calc_lines.append(f"short_condition = {s_cond_str}")
    
    sections.append("\n".join(calc_lines))

    # [3. 진입 및 청산 실행 섹션]
    order_lines = [
        "\n// ==========================================",
        "// 3. ORDER EXECUTION & RISK MANAGEMENT (현물 롱 전용)",
        "// ==========================================",
        "var float long_entry_price = na",
        "",
        "// 롱 포지션 진입 (현물 매수)",
        "if long_condition and strategy.position_size == 0",
        '    strategy.entry("Long", strategy.long, comment="Entry_Long")',
        "    long_entry_price := close",
        "",
        "// 익절(Take Profit) & 손절(Stop Loss) 계산",
        "fixed_long_tp = long_entry_price * (1.0 + tp_fixed_pct * 0.01)",
        "fixed_long_sl = long_entry_price * (1.0 - sl_fixed_pct * 0.01)",
        "atr_long_tp   = long_entry_price + (tp_atr_mult * atr_val)",
        "atr_long_sl   = long_entry_price - (sl_atr_mult * atr_val)",
        "",
        'final_long_tp = tp_mode == "Fixed" ? fixed_long_tp : (tp_mode == "ATR" ? atr_long_tp : (tp_mode == "Both" ? math.max(fixed_long_tp, atr_long_tp) : na))',
        'final_long_sl = sl_mode == "Fixed" ? fixed_long_sl : (sl_mode == "ATR" ? atr_long_sl : (sl_mode == "Both" ? math.max(fixed_long_sl, atr_long_sl) : na))',
        "",
        "// 익절/손절 청산 주문",
        'if strategy.position_size > 0',
        '    strategy.exit("TP/SL_Long", "Long", limit=final_long_tp, stop=final_long_sl)',
        "",
        "// 하락/반전 신호 발생 시 현금화 청산 (현물 매도)",
        'if strategy.position_size > 0 and short_condition',
        '    strategy.close("Long", comment="Exit_Signal")'
    ]
    
    # 비상 탈출 로직
    if use_tr:
        order_lines.extend([
            "",
            "// TR MA 비상 청산",
            "if strategy.position_size > 0 and close < tr_ma",
            '    strategy.close("Long", comment="TR_MA_Exit")'
        ])
        
    if use_time:
        order_lines.extend([
            "",
            "// 시간 만기 청산 (Time Expiry)",
            "bars_in_trade = ta.barssince(strategy.position_size != strategy.position_size[1])",
            "if use_time_exit and (bars_in_trade >= max_bars_hold)",
            '    if strategy.position_size > 0',
            '        strategy.close("Long", comment="Time_Expiry")'
        ])
        
    sections.append("\n".join(order_lines))

    # [4. 차트 시각화 섹션]
    vis_lines = [
        "\n// ==========================================",
        "// 4. CHART VISUALIZATION (전략 맞춤 시각화)",
        "// =========================================="
    ]
    
    if strat_type == 'SuperTrend_Trend':
        vis_lines.append('plot(st_line, "SuperTrend", color=(st_dir == -1 ? color.green : color.red), linewidth=2)')
        vis_lines.append('bgcolor(st_dir == -1 ? color.new(color.green, 93) : color.new(color.red, 93), title="Regime Background")')
    elif strat_type == 'EMA_Cross':
        vis_lines.append('plot(fast_ema, "Fast EMA", color=color.aqua, linewidth=2)')
        vis_lines.append('plot(slow_ema, "Slow/Macro EMA", color=color.orange, linewidth=2)')
    elif strat_type == 'Squeeze_Breakout':
        vis_lines.append('plotshape(trig_long, title="Squeeze Bull", style=shape.triangleup, location=location.belowbar, color=color.green, size=size.small)')
        vis_lines.append('plotshape(trig_short, title="Squeeze Bear", style=shape.triangledown, location=location.abovebar, color=color.red, size=size.small)')
    elif strat_type == 'SMC_Structure':
        vis_lines.append('plot(last_ph, "Swing High (BOS Level)", color=color.red, style=plot.style_circles)')
        vis_lines.append('plot(last_pl, "Swing Low (BOS Level)", color=color.green, style=plot.style_circles)')
        vis_lines.append('plotshape(bull_bos, title="BOS Breakout", style=shape.diamond, location=location.belowbar, color=color.green, size=size.small)')
    elif strat_type == 'RSI_Reversal':
        vis_lines.append('plotshape(trig_long, title="RSI Reversal Long", style=shape.triangleup, location=location.belowbar, color=color.blue, size=size.small)')
        vis_lines.append('plotshape(trig_short, title="RSI Reversal Short", style=shape.triangledown, location=location.abovebar, color=color.fuchsia, size=size.small)')

    if use_ema:
        vis_lines.append('plot(use_ema_filter ? macro_ema : na, "Macro EMA", color=color.new(color.orange, 40), linewidth=2)')
    if use_tr:
        vis_lines.append('plot(use_tr_exit ? tr_ma : na, "TR MA Emergency", color=color.new(color.purple, 30), linewidth=2)')
        
    sections.append("\n".join(vis_lines))
    
    return "\n".join(sections)

# =========================================================================
# 유전 진화 탐색 엔진 (Genetic Evolutionary Algorithm Engine)
# =========================================================================

# 유전자 정의 (Gene Map: 5대 독립 전략 아키텍처 및 퀀트 파라미터)
GENE_OPTIONS = {
    'strategy_type': STRATEGY_TYPE_KEYS,  # 5대 매매 알고리즘 아키텍처 중 최적 모델 자율 선별
    'st_period': [7, 9, 10, 12, 14, 20],
    'st_mult': [2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
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
    'adx_threshold': [20.0, 25.0, 30.0, 35.0],
    'vol_ma_len': [10, 20, 30, 50],
    'vol_mult': [0.8, 1.0, 1.2, 1.5],
    'tr_ma_len': [30, 50, 80, 100, 150, 200],
    'tp_mode': ['None', 'Fixed', 'ATR', 'Both'],
    'sl_mode': ['Fixed', 'ATR', 'Both'],
    'tp_fixed_pct': [10.0, 20.0, 35.0, 50.0, 80.0, 120.0, 200.0],
    'sl_fixed_pct': [1.5, 2.0, 2.5, 3.0, 4.0],
    'tp_atr_mult': [4.0, 6.0, 8.0, 12.0, 16.0, 24.0],
    'sl_atr_mult': [1.5, 2.0, 2.5, 3.0],
    'max_bars_hold': [72, 120, 240, 480, 720, 1440]
}

def _evaluate_fitness(sim_res, min_trades=50, max_mdd_allowed=35.0):
    """
    [현물 롱 전용(Spot Long-Only) 실전 퀀트 적합도 함수 (Fitness Function)]
    - 복리 수익률 왜곡(단일 고빈도 전략의 수십만 점 폭발 독점)을 방지하기 위해 로그 스케일 적용
    - 위험 대비 수익비(샤프 지수) 및 MDD 방어력, 승률에 높은 가중치 부여
    - 오버트레이딩(과도한 잦은 매매로 인한 수수료 누적) 억제 및 표본 신뢰도 확보
    """
    oos = sim_res['oos']
    is_res = sim_res['is']
    trades = oos.get('trades_count', 0)
    
    # 1. 최소 거래수 검증: 표본 부족에 의한 우연한 수익 원천 배제 (현물 스윙 기준 50회)
    if trades < min_trades:
        return -2000.0 - (min_trades - trades) * 15.0
        
    oos_sh = oos.get('sharpe', 0.0)
    oos_ret = oos.get('return_pct', 0.0)
    oos_mdd = abs(oos.get('mdd', 0.0))
    win_rate = oos.get('win_rate', 0.0)
    overfitting_ratio = sim_res.get('overfitting_ratio', 1.0)
    
    # 마이너스 수익률 탈락 처리
    if oos_ret <= 0.0:
        return -1000.0 + oos_ret
        
    score = 0.0
    
    # 2. [OOS 샤프 지수 핵심 배점 (위험 대비 보상)]
    if oos_sh > 0:
        score += min(oos_sh, 10.0) * 15.0
        
    # 3. [승률 50% 이상 가산점 & 미만 감점]
    if win_rate >= 50.0:
        score += 25.0 + (win_rate - 50.0) * 2.0
    else:
        score -= (50.0 - win_rate) * 1.5
        
    # 4. [로그 스케일 수익률 점수: 특정 전략의 비정상적 복리 폭발 독점 차단]
    score += np.log1p(oos_ret) * 12.0
    if oos_ret >= 50.0:
        score += 15.0
    if oos_ret >= 100.0:
        score += 20.0
    if oos_ret >= 300.0:
        score += 20.0
    if oos_ret >= 500.0:
        score += 20.0
    if oos_ret >= 1000.0:
        score += 25.0
        
    # 5. [MDD 방어력 배점]
    if oos_mdd > max_mdd_allowed:
        score -= (oos_mdd - max_mdd_allowed) * 5.0
    else:
        score += (max_mdd_allowed - oos_mdd) * 1.5 # 낮은 MDD 우대
        
    # 6. [WFO 일반화 능력 검증 (과최적화 방지)]
    if 0.5 <= overfitting_ratio <= 1.8:
        score += 15.0
    elif overfitting_ratio < 0.3:
        score -= 25.0
        
    # 7. [현물 실전 거래수 최적 구간 (30~350회 우대, 과도한 잦은 매매 페널티)]
    if 40 <= trades <= 350:
        score += 15.0
    elif trades > 800:
        score -= 20.0 # 현물에서 잦은 매매는 거래소 수수료 누적으로 실전 손실 유발
        
    return score

def _worker_simulate(task_args):
    """초고속 무누수(Zero-Leak) 개별 시뮬레이션 단위"""
    df_data, cand, min_trades, max_mdd = task_args
    sim_res = run_simulation(df_data, cand, split_ratio=0.70, fast_mode=True)
    score = _evaluate_fitness(sim_res, min_trades=min_trades, max_mdd_allowed=max_mdd)
    
    return {
        'score': score,
        'params': cand,
        'sim_res': sim_res
    }

def run_ai_evolution_search(df, symbol="BTC/USDT", timeframe="1h", max_iterations=1000000, min_trades=50, max_mdd=35.0, num_workers=None, progress_callback=None, cancel_check=None, recent_history=None, seed=None):
    """차트 적응형 탐색, 유형별 균등 진화 및 생성 이력 기반 다양성 선택."""
    from strategy_search import run_search
    return run_search(df, symbol, timeframe, max_iterations, min_trades, max_mdd,
                      num_workers, progress_callback, cancel_check, recent_history, seed)
