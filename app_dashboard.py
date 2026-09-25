import os
import glob
import time
import datetime
import pandas as pd
import numpy as np

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

import streamlit as st
from data_manager import get_cached_data
from quant_engine import run_simulation
from report_exporter import export_backtest_to_excel
from ai_generator import generate_pine_script_v6
from discord_notifier import send_strategy_alert, send_test_alert, DEFAULT_WEBHOOK_URL
from evolution_manager import (
    get_job_status,
    get_latest_strategy,
    list_strategy_history,
    load_strategy_history,
    start_background_evolution
)

st.set_page_config(page_title="AI 퀀트 리서치 터미널 v6.0", page_icon="⚡", layout="wide")

# [스크롤 최적화 및 GPU 가속 CSS 주입]
st.markdown("""
<style>
/* 부드러운 스크롤 애니메이션 활성화 */
html {
    scroll-behavior: smooth !important;
}
/* 브라우저 GPU 렌더링 가속화 */
.stApp {
    -webkit-overflow-scrolling: touch;
    transform: translateZ(0);
    -webkit-transform: translateZ(0);
}
/* 무거운 차트 컨테이너 레이아웃 격리 (스크롤 리플로우 & 랙 방지) */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
    contain: content;
    will-change: transform;
}
/* 부드럽고 가벼운 스크롤바 */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.4);
}
</style>
""", unsafe_allow_html=True)

def downsample_for_chart(series, max_points=600):
    """
    수만 개 캔들 차트를 60FPS로 부드럽게 렌더링하도록 지능적 다운샘플링
    (형태와 변곡점은 100% 보존하면서 브라우저 DOM 렌더링 부하와 스크롤 랙 완벽 해소)
    """
    if series is None or len(series) <= max_points:
        return series
    step = max(1, len(series) // max_points)
    sampled = series.iloc[::step].copy()
    if len(series) > 0 and (len(sampled) == 0 or sampled.index[-1] != series.index[-1]):
        sampled = pd.concat([sampled, series.iloc[[-1]]])
    return sampled

# CPU 코어 감지
detected_cores = os.cpu_count() or 1

# ----------------- [사이드바 컨트롤 패널] -----------------
with st.sidebar:
    st.title("⚙️ 퀀트 컨트롤 패널")
    st.success(f"🖥️ 서버 CPU 코어: **{detected_cores} Core** 감지됨")
    
    st.markdown("### 1. 분석 대상 차트 설정")
    sym_presets = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "BNB/USDT", "ADA/USDT", "AVAX/USDT", "SUI/USDT", "직접 입력 (Custom)"]
    sym_choice = st.selectbox("거래 종목 선택", sym_presets, index=0)
    if sym_choice == "직접 입력 (Custom)":
        symbol_input = st.text_input("직접 입력할 심볼 (예: LINK/USDT, PEPE/USDT)", value="LINK/USDT").strip().upper()
        symbol = symbol_input if symbol_input else "BTC/USDT"
    else:
        symbol = sym_choice

    tf_presets = ["5m", "15m", "30m", "1h", "2h", "4h", "1d", "직접 입력 (Custom)"]
    tf_choice = st.selectbox("타임프레임 (주기)", tf_presets, index=3)
    if tf_choice == "직접 입력 (Custom)":
        tf_input = st.text_input("타임프레임 직접 입력 (1m, 3m, 5m, 15m, 1h, 2h, 4h, 1d 등)", value="1h").strip().lower()
        timeframe = tf_input if tf_input else "1h"
    else:
        timeframe = tf_choice

    start_year = st.selectbox("데이터 시작 연도", ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025"], index=0, help="Binance 상장 시점부터 현재까지의 시계열 데이터를 자동 수집 및 로컬 캐싱합니다.")
    start_date = f"{start_year}-01-01"

    st.markdown("---")
    mode = st.radio("모드 선택", ["🤖 AI 에이전트 자율 전략 생성", "🛠️ 수동 파라미터 백테스트"], index=0)
    
    if mode == "🛠️ 수동 파라미터 백테스트":
        st.markdown("### 2. 전략 파라미터 튜닝")
        with st.expander("🚀 SuperTrend 엔진", expanded=True):
            st_period = st.slider("SuperTrend Period", 3, 21, 7)
            st_mult = st.slider("SuperTrend Multiplier", 1.5, 5.0, 3.0, 0.1)
            
        with st.expander("⚡ Squeeze Momentum (LazyBear)", expanded=True):
            use_squeeze = st.checkbox("Squeeze Momentum 필터 사용", value=True)
            sqz_len = st.number_input("Squeeze Length", 10, 50, 20, 1)
            bb_mult = st.slider("BB StdDev Multiplier", 1.0, 3.0, 2.0, 0.1)
            kc_mult = st.slider("KC ATR Multiplier", 1.0, 3.0, 1.5, 0.1)

        with st.expander("💡 Smart Money Concepts (SMC)", expanded=True):
            use_smc = st.checkbox("Smart Money Concepts 필터 사용", value=False)
            smc_swing_len = st.slider("SMC Swing Length (Pivot)", 2, 15, 5)
            smc_mode = st.selectbox("SMC 판정 모드", ["Structure", "FVG", "Both"], index=0)

        with st.expander("📈 RSI (상대강도지수 & 과매수/과매도)", expanded=False):
            use_rsi = st.checkbox("RSI 필터 사용", value=False)
            rsi_len = st.number_input("RSI Length", 5, 50, 14, 1)
            rsi_mode = st.selectbox("RSI 필터 모드", ["Boundary", "Momentum"], index=0, help="Boundary: 과열 진입 제한 / Momentum: 50선 추세 정렬")
            c_rsi1, c_rsi2 = st.columns(2)
            with c_rsi1: rsi_ob = st.number_input("과매수 제한 (OB)", 50.0, 95.0, 70.0, 5.0)
            with c_rsi2: rsi_os = st.number_input("과매도 제한 (OS)", 5.0, 50.0, 30.0, 5.0)

        with st.expander("🌪️ ADX (추세 강도 필터)", expanded=False):
            use_adx = st.checkbox("ADX 추세 강도 필터 사용", value=False)
            adx_len = st.number_input("ADX Length", 5, 50, 14, 1)
            adx_threshold = st.slider("최소 ADX 추세 강도", 10.0, 50.0, 20.0, 1.0, help="ADX가 이 기준 이상일 때만 추세 진입 허용(횡보장 휩소 차단)")

        with st.expander("📊 Volume MA (거래량 수급 확인)", expanded=False):
            use_vol = st.checkbox("거래량 수급 필터 사용", value=False)
            vol_ma_len = st.number_input("거래량 MA Length", 5, 100, 20, 5)
            vol_mult = st.slider("거래량 배수", 0.5, 3.0, 1.0, 0.1, help="현재 거래량이 거래량 MA의 N배 이상일 때만 진입")

        with st.expander("🛡️ 거시 레짐 & 변동성 필터", expanded=False):
            use_ema_filter = st.checkbox("거시 EMA 필터 사용", value=True)
            ema_len = st.number_input("Macro EMA Length", 50, 400, 200, 10)
            use_min_volat = st.checkbox("최소 변동성(Min Width) 필터 사용", value=True)
            min_width_pct = st.slider("최소 변동폭 (%)", 0.5, 3.0, 1.5, 0.1)
            
        with st.expander("🚨 TR MA 비상 탈출 라인", expanded=False):
            use_tr_exit = st.checkbox("TR MA 이탈 시 비상 청산", value=True)
            tr_ma_len = st.number_input("TR MA Length", 20, 200, 100, 10)
            
        with st.expander("🎯 하이브리드 TP / SL 엔진", expanded=False):
            tp_mode = st.selectbox("익절(TP) 모드", ["None", "Fixed", "ATR", "Both"], index=2)
            sl_mode = st.selectbox("손절(SL) 모드", ["None", "Fixed", "ATR", "Both"], index=2)
            c_tp1, c_tp2 = st.columns(2)
            with c_tp1: tp_fixed_pct = st.number_input("고정 TP (%)", 0.5, 10.0, 3.0, 0.5)
            with c_tp2: tp_atr_mult = st.number_input("ATR TP 배수", 1.0, 6.0, 3.5, 0.5)
            c_sl1, c_sl2 = st.columns(2)
            with c_sl1: sl_fixed_pct = st.number_input("고정 SL (%)", 0.5, 10.0, 2.0, 0.5)
            with c_sl2: sl_atr_mult = st.number_input("ATR SL 배수", 1.0, 5.0, 2.0, 0.5)
            
        with st.expander("⏱️ 시간 만기 청산", expanded=False):
            use_time_exit = st.checkbox("시간 만기 청산 활성화", value=True)
            max_bars_hold = st.number_input("최대 보유 봉 수", 12, 168, 72, 6)

        btn_manual_run = st.button("🚀 백테스트 실행", type="primary", use_container_width=True)
        btn_ai_run = False
        workers_to_use = 1
    else:
        st.markdown("### 2. 🧬 AI 다세대 유전 진화 설정")
        preset = st.radio(
            "탐색 강도 프리셋",
            ["⚡ 빠른 스캔 (1,000회)", "🔬 심층 퀀트 진화 (3,000회)", "🔥 울트라 고수익 진화 (5,000회)", "🚀 극한 알파 탐색 (10,000회 / 기본값)", "🎛️ 직접 설정"],
            index=3,
            help="심층 진화일수록 다세대(Multi-Generation) 교차 및 돌연변이를 거쳐 초고수익/고승률과 리스크 통제를 동시에 달성합니다."
        )
        
        if "1,000회" in preset:
            ai_iterations = 1000
        elif "3,000회" in preset:
            ai_iterations = 3000
        elif "5,000회" in preset:
            ai_iterations = 5000
        elif "10,000회" in preset:
            ai_iterations = 10000
        else:
            ai_iterations = st.number_input("탐색 개체 수 (Iterations)", min_value=100, max_value=50000, value=10000, step=1000)
            
        col_set1, col_set2 = st.columns(2)
        with col_set1:
            max_mdd = st.number_input(
                "최대 허용 MDD (%)", 
                min_value=10.0, max_value=80.0, value=40.0, step=5.0,
                help="MDD가 40% 이내면 정상 추세 변동성으로 허용하며, 40%를 초과할 경우 강력한 탈락 페널티를 부과합니다."
            )
        with col_set2:
            min_trades = st.number_input(
                "최소 검증 거래수", 
                min_value=10, max_value=500, value=100, step=10,
                help="OOS 구간에서 최소 이 횟수 이상 실제 체결된 전략만 최종 선별됩니다."
            )
        
        default_workers = min(detected_cores, 8)
        workers_to_use = st.number_input(f"병렬 가속 워커 수 (최대 {detected_cores})", 1, detected_cores, default_workers)
        
        st.info(f"🧬 **고수익 유전 진화 풀가동**: 8대 퀀트 지표군을 {workers_to_use}개 CPU 코어로 {ai_iterations:,}회 유전 진화 탐색하여, MDD {max_mdd:.0f}% 한도 내에서 승률 50%+ & 1,000%+ 수익률을 지향하는 Pine Script v6 코드를 합성합니다.")
        btn_ai_run = st.button("🤖 AI 심층 진화 & 고수익 전략 생성", type="primary", use_container_width=True)
        btn_manual_run = False

    st.markdown("---")
    with st.expander("🔔 Discord 웹훅 알림 설정", expanded=False):
        use_discord = st.checkbox("진행 상황(25%, 50%, 75%, 완성) 웹훅 알림", value=True)
        webhook_url = st.text_input("Discord Webhook URL", value=DEFAULT_WEBHOOK_URL)
        if st.button("🔔 디스코드 연결 테스트", use_container_width=True):
            if send_test_alert(webhook_url):
                st.success("✅ 디스코드 알림 전송 성공!")
            else:
                st.error("❌ 전송 실패! 웹훅 URL을 확인해 주세요.")

# ----------------- [메인 대시보드 상단] -----------------
st.title("⚡ AI QUANTUM RESEARCH TERMINAL v6.0")
st.caption(f"선택 심볼: **{symbol}** | 주기: **{timeframe}** | 감지된 서버 코어: **{detected_cores} Cores**")

def draw_metric(col, label, val_is, val_oos, color="#34C759"):
    col.markdown(f"""
    <div style='background: #ffffff; border-radius: 10px; padding: 14px; border: 1px solid #e0e0e0; box-shadow: 0 2px 4px rgba(0,0,0,0.04);'>
        <p style='color: #666; font-size: 0.85em; margin: 0; font-weight: 500;'>{label}</p>
        <h3 style='color: {color}; margin: 6px 0 4px 0;'>{val_oos}</h3>
        <p style='color: #888; font-size: 0.75em; margin: 0;'>IS: {val_is} | OOS: {val_oos}</p>
    </div>
    """, unsafe_allow_html=True)

# ----------------- [1. 백그라운드 작업 상태 모니터링 & 자동 복원] -----------------
current_job = get_job_status()
is_job_running = current_job.get("status") == "RUNNING"

if is_job_running:
    pct = current_job.get("progress_pct", 0)
    g_curr = current_job.get("generation", 1)
    g_tot = current_job.get("total_generations", 5)
    b_ret = current_job.get("best_return", 0.0)
    b_wr = current_job.get("best_win_rate", 0.0)
    b_mdd = current_job.get("best_mdd", 0.0)
    b_tr = current_job.get("best_trades", 0)
    elap = int(current_job.get("elapsed_sec", 0))
    elap_str = f"{elap // 60}분 {elap % 60}초" if elap >= 60 else f"{elap}초"
    
    st.info(f"""
    ### 🧬 AI 다세대 유전 진화 백그라운드 가동 중 (무중단 모드)
    - **대상 종목**: `{current_job.get('symbol', symbol)}` ({current_job.get('timeframe', timeframe)}) | **탐색 규모**: {current_job.get('max_iterations', 10000):,}회
    - **현재 진행률**: **{pct}%** (제 {g_curr}/{g_tot} 세대 진화 중) | **경과 시간**: {elap_str}
    - 💰 **현재 최고 수익률**: **{b_ret:+.1f}%** | 🎯 **승률**: **{b_wr:.1f}%** ({b_tr}회 거래) | 🛡️ **MDD**: **{b_mdd:.1f}%**
    
    > 🛡️ **무중단 안내**: 브라우저 창을 닫으시거나 자리를 비우셔도 서버 백그라운드에서 **10,000회 끝까지 끊김 없이 계속 연산**됩니다.  
    > **25%, 50%, 75%, 100%** 달성 시마다 디스코드로 리포트가 자동 전송되며, 완료 후 언제 접속하셔도 완성된 전략 코드가 화면에 즉시 복원됩니다.
    """)
    st.progress(pct / 100.0)
    time.sleep(2)
    st.rerun()

# ----------------- [2. AI 자율 생성 버튼 핸들러 (백그라운드 시작)] -----------------
if btn_ai_run:
    if is_job_running:
        st.warning("⚠️ 이미 백그라운드에서 유전 진화 탐색이 실행 중입니다. 완료 후 새로운 작업을 시작해 주세요.")
    else:
        with st.spinner(f"'{symbol}' ({timeframe}) {start_year}년~현재 데이터 수집 및 백그라운드 워커 기동 중..."):
            try:
                df = get_cached_data(symbol, timeframe, start_date=start_date)
            except Exception as e:
                st.error(f"❌ 데이터 로드 실패: {symbol} ({timeframe}) 데이터를 가져올 수 없습니다. ({e})")
                df = None
                
            if df is not None:
                success, msg = start_background_evolution(
                    df=df,
                    symbol=symbol,
                    timeframe=timeframe,
                    max_iterations=ai_iterations,
                    min_trades=min_trades,
                    max_mdd=max_mdd,
                    num_workers=workers_to_use,
                    webhook_url=webhook_url if use_discord else None,
                    use_discord=use_discord
                )
                if success:
                    st.success("🚀 백그라운드 유전 진화가 시작되었습니다! 브라우저 창을 닫으셔도 계속 실행됩니다.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning(msg)

# ----------------- [3. 수동 백테스트 모드 핸들러] -----------------
if btn_manual_run:
    with st.spinner(f"⏳ '{symbol}' ({timeframe}) {start_year}년~현재 시계열 데이터 로드 및 백테스트 연산 중..."):
        try:
            df = get_cached_data(symbol, timeframe, start_date=start_date)
        except Exception as e:
            st.error(f"❌ 데이터 로드 실패: {symbol} ({timeframe}) 데이터를 가져올 수 없습니다. ({e})")
            df = None

        if df is not None:
            params = {
                'st_period': st_period, 'st_mult': st_mult,
                'use_squeeze': use_squeeze, 'sqz_len': sqz_len, 'bb_mult': bb_mult, 'kc_mult': kc_mult,
                'use_smc': use_smc, 'smc_swing_len': smc_swing_len, 'smc_mode': smc_mode,
                'use_rsi': use_rsi, 'rsi_len': rsi_len, 'rsi_mode': rsi_mode, 'rsi_ob': rsi_ob, 'rsi_os': rsi_os,
                'use_adx': use_adx, 'adx_len': adx_len, 'adx_threshold': adx_threshold,
                'use_vol': use_vol, 'vol_ma_len': vol_ma_len, 'vol_mult': vol_mult,
                'ema_len': ema_len, 'use_ema_filter': use_ema_filter,
                'min_width_pct': min_width_pct, 'use_min_volat': use_min_volat,
                'tr_ma_len': tr_ma_len, 'use_tr_exit': use_tr_exit,
                'tp_mode': tp_mode, 'sl_mode': sl_mode,
                'tp_fixed_pct': tp_fixed_pct, 'sl_fixed_pct': sl_fixed_pct,
                'tp_atr_mult': tp_atr_mult, 'sl_atr_mult': sl_atr_mult,
                'use_time_exit': use_time_exit, 'max_bars_hold': max_bars_hold
            }
            res = run_simulation(df, params, split_ratio=0.70)
            summary = {
                'symbol': symbol, 'timeframe': timeframe,
                'oos_sharpe': res['oos']['sharpe'], 'oos_return': res['oos']['return_pct'],
                'oos_mdd': res['oos']['mdd'], 'oos_win_rate': res['oos']['win_rate'],
                'oos_trades': res['oos']['trades_count']
            }
            pine_code = generate_pine_script_v6(f"Custom {symbol} {timeframe} Strategy v6", params, summary)
            
            # 수동 결과 세션 저장
            st.session_state["active_strategy"] = {
                "symbol": symbol, "timeframe": timeframe,
                "oos_sharpe": res['oos']['sharpe'], "oos_return": res['oos']['return_pct'],
                "oos_mdd": res['oos']['mdd'], "oos_win_rate": res['oos']['win_rate'],
                "oos_trades": res['oos']['trades_count'],
                "is_sharpe": res['is']['sharpe'], "is_return": res['is']['return_pct'],
                "is_mdd": res['is']['mdd'], "is_win_rate": res['is']['win_rate'],
                "is_trades": res['is']['trades_count'],
                "best_params": params,
                "pine_code": pine_code,
                "is_equity": res['is']['equity'],
                "oos_equity": res['oos']['equity'],
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if use_discord and webhook_url:
                send_strategy_alert(
                    webhook_url=webhook_url,
                    mode_name="🛠️ 수동 백테스트",
                    symbol=symbol,
                    timeframe=timeframe,
                    oos_metrics=res['oos'],
                    is_metrics=res['is'],
                    params=params
                )
                st.toast("🔔 디스코드로 전략 생성 알림이 전송되었습니다!")

# ----------------- [4. 전략 결과 자동 복원 및 렌더링] -----------------
# 세션에 활성 전략이 없으면 디스크에서 최신 완료 전략 자동 로드
active_strat = st.session_state.get("active_strategy")
if active_strat is None and not is_job_running:
    latest_saved = get_latest_strategy()
    if latest_saved:
        active_strat = latest_saved
        st.session_state["active_strategy"] = active_strat
        st.success(
            f"💾 **최근 완료된 전략 자동 복원됨**: [{active_strat['symbol']} {active_strat['timeframe']}] "
            f"생성 일시: {active_strat.get('created_at', '최근')} | OOS 수익률: **{active_strat.get('oos_return', 0.0):+.1f}%** | "
            f"승률: **{active_strat.get('oos_win_rate', 0.0):.1f}%** | MDD: **{active_strat.get('oos_mdd', 0.0):.1f}%**  \n"
            f"(오래 켜두어 화면이 새로고침되거나 브라우저를 다시 열어도 결과가 안전하게 보존됩니다.)"
        )

if active_strat is not None and not is_job_running:
    # 텔레메트리 메트릭 5종 카드
    c1, c2, c3, c4, c5 = st.columns(5)
    sh_oos = active_strat.get('oos_sharpe', 0.0)
    sh_is = active_strat.get('is_sharpe', 0.0)
    ret_oos = active_strat.get('oos_return', 0.0)
    ret_is = active_strat.get('is_return', 0.0)
    mdd_oos = active_strat.get('oos_mdd', 0.0)
    mdd_is = active_strat.get('is_mdd', 0.0)
    wr_oos = active_strat.get('oos_win_rate', 0.0)
    wr_is = active_strat.get('is_win_rate', 0.0)
    tr_oos = active_strat.get('oos_trades', 0)
    tr_is = active_strat.get('is_trades', 0)

    draw_metric(c1, "🏆 OOS 샤프 지수", f"{sh_is:.2f}", f"{sh_oos:.2f}", "#007aff" if sh_oos >= 1.0 else "#ff9500")
    draw_metric(c2, "📈 누적 수익률", f"{ret_is:+.1f}%", f"{ret_oos:+.1f}%", "#d97706" if ret_oos >= 1000.0 else "#34C759" if ret_oos > 0 else "#ff3b30")
    draw_metric(c3, "🛡️ 최대 낙폭 (MDD)", f"{mdd_is:.1f}%", f"{mdd_oos:.1f}%", "#ff3b30" if abs(mdd_oos) > 40.0 else "#34C759")
    draw_metric(c4, "🎯 승률 (Win Rate)", f"{wr_is:.1f}%", f"{wr_oos:.1f}%", "#007aff" if wr_oos >= 50.0 else "#5856d6")
    draw_metric(c5, "🔄 OOS 거래 횟수", f"{tr_is}회", f"{tr_oos}회", "#ff9500")

    st.divider()
    
    # 에쿼티 커브 차트
    st.subheader(f"📊 누적 자산 성장 곡선 (Equity Curve: {active_strat['symbol']} {active_strat['timeframe']})")
    
    # equity 데이터 시리즈 복원
    is_eq_raw = active_strat.get('is_equity', {})
    oos_eq_raw = active_strat.get('oos_equity', {})
    
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.markdown("**In-Sample (과거 70% 학습 구간)**")
        if isinstance(is_eq_raw, pd.Series):
            st.line_chart(downsample_for_chart(is_eq_raw), color="#007aff")
        elif isinstance(is_eq_raw, dict) and len(is_eq_raw) > 0:
            st.line_chart(pd.Series(is_eq_raw), color="#007aff")
        else:
            st.caption("에쿼티 데이터 없음")
            
    with col_chart2:
        st.markdown("**Out-of-Sample (최근 30% 미지의 검증 구간)**")
        if isinstance(oos_eq_raw, pd.Series):
            st.line_chart(downsample_for_chart(oos_eq_raw), color="#34C759")
        elif isinstance(oos_eq_raw, dict) and len(oos_eq_raw) > 0:
            st.line_chart(pd.Series(oos_eq_raw), color="#34C759")
        else:
            st.caption("에쿼티 데이터 없음")

    st.divider()
    
    # 📝 AI가 합성한 Pine Script v6 코드 뷰어
    st.subheader("🤖 AI 에이전트가 자동 합성한 Pine Script v6 전략 코드 (8대 퀀트 지표 융합)")
    st.caption("아래 코드는 선택한 차트에 대해 SuperTrend, Macro EMA, Squeeze, SMC, RSI, ADX, Volume MA 등 유전 진화로 엄선된 최적 지표 조합과 리스크 관리 엔진으로 작성된 공식 Pine Script v6 코드입니다.")
    
    code_text = active_strat.get("pine_code", "")
    st.text_area("Pine Script Code", value=code_text, height=350)
    
    c_btn1, c_btn2 = st.columns(2)
    strat_sym_clean = active_strat['symbol'].replace('/', '')
    strat_tf_clean = active_strat['timeframe']
    with c_btn1:
        st.download_button(
            "💾 파인스크립트 파일 다운로드 (.pine)",
            code_text,
            file_name=f"strategy_{strat_sym_clean}_{strat_tf_clean}_v6.pine",
            use_container_width=True
        )
    with c_btn2:
        if st.button("📋 로컬 strategy_v6.pine 덮어쓰기 저장", use_container_width=True):
            with open("strategy_v6.pine", "w", encoding="utf-8") as f:
                f.write(code_text)
            st.success("✅ 'strategy_v6.pine' 파일로 성공적으로 저장되었습니다!")

    # 📜 과거 전략 히스토리 보관함
    st.divider()
    with st.expander("📜 과거 생성된 전략 히스토리 보관함 (영구 보존 목록)", expanded=False):
        history_list = list_strategy_history()
        if len(history_list) == 0:
            st.caption("아직 보관된 과거 전략이 없습니다.")
        else:
            hist_options = [
                f"[{h['timestamp']}] {h['symbol']} ({h['timeframe']}) - 수익률: {h['return_pct']:+.1f}% | 승률: {h['win_rate']:.1f}% | MDD: {h['mdd']:.1f}%"
                for h in history_list
            ]
            selected_hist_idx = st.selectbox("불러올 전략 선택", range(len(hist_options)), format_func=lambda i: hist_options[i])
            if st.button("📂 선택한 전략 화면에 불러오기", use_container_width=True):
                chosen_file = history_list[selected_hist_idx]['filepath']
                loaded = load_strategy_history(chosen_file)
                if loaded:
                    st.session_state["active_strategy"] = loaded
                    st.success(f"✅ [{loaded['symbol']} {loaded['timeframe']}] 전략을 성공적으로 불러왔습니다!")
                    time.sleep(1)
                    st.rerun()

elif not is_job_running:
    st.info("👈 좌측 사이드바에서 [🤖 AI 심층 진화 & 고수익 전략 생성] 버튼을 누르시면, 백그라운드에서 10,000회 유전 진화가 시작되며 25%, 50%, 75%, 100% 달성 시 디스코드로 자동 보고됩니다.")
