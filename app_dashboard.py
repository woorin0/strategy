import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
import glob
from data_manager import get_cached_data
from quant_engine import run_simulation
from report_exporter import export_backtest_to_excel
from ai_generator import run_ai_evolution_search, generate_pine_script_v6

st.set_page_config(page_title="AI 퀀트 리서치 터미널 v6.0", page_icon="⚡", layout="wide")

# ----------------- [사이드바 컨트롤 패널] -----------------
with st.sidebar:
    st.title("⚙️ 퀀트 컨트롤 패널")
    
    st.markdown("### 1. 분석 대상 차트 설정")
    symbol = st.selectbox("거래 종목 (Symbol)", ["BTC/USDT", "ETH/USDT", "SOL/USDT"], index=0)
    timeframe = st.selectbox("타임프레임 (주기)", ["15m", "1h", "4h"], index=1)
    
    st.markdown("---")
    mode = st.radio("모드 선택", ["🤖 AI 에이전트 자율 전략 생성", "🛠️ 수동 파라미터 백테스트"], index=0)
    
    if mode == "🛠️ 수동 파라미터 백테스트":
        st.markdown("### 2. 전략 파라미터 튜닝")
        with st.expander("🚀 SuperTrend 엔진", expanded=True):
            st_period = st.slider("SuperTrend Period", 3, 21, 7)
            st_mult = st.slider("SuperTrend Multiplier", 1.5, 5.0, 3.0, 0.1)
            
        with st.expander("🛡️ 거시 레짐 & 변동성 필터", expanded=True):
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
    else:
        st.markdown("### 2. AI 에이전트 자율 진화 설정")
        ai_iterations = st.slider("탐색 세대 수 (Iterations)", 5, 50, 20, 5)
        st.info("💡 AI 에이전트가 설정된 차트 시계열을 70% In-Sample과 30% Out-of-Sample로 분할 분석하여, 과적합을 차단한 최적의 새로운 파인스크립트 v6 전략을 자동으로 합성합니다.")
        btn_ai_run = st.button("🤖 AI 자율 분석 및 전략 코드 생성", type="primary", use_container_width=True)
        btn_manual_run = False

# ----------------- [메인 대시보드] -----------------
st.title("⚡ AI QUANTUM RESEARCH TERMINAL v6.0")
st.caption(f"선택 심볼: **{symbol}** | 주기: **{timeframe}** | 모드: **{mode}**")

def draw_metric(col, label, val_is, val_oos, color="#34C759"):
    col.markdown(f"""
    <div style='background: #ffffff; border-radius: 10px; padding: 14px; border: 1px solid #e0e0e0; box-shadow: 0 2px 4px rgba(0,0,0,0.04);'>
        <p style='color: #666; font-size: 0.85em; margin: 0; font-weight: 500;'>{label}</p>
        <h3 style='color: {color}; margin: 6px 0 4px 0;'>{val_oos}</h3>
        <p style='color: #888; font-size: 0.75em; margin: 0;'>IS: {val_is} | OOS: {val_oos}</p>
    </div>
    """, unsafe_allow_html=True)

# ----------------- [AI 에이전트 자율 생성 모드 로직] -----------------
if btn_ai_run:
    prog_bar = st.progress(0, text="데이터 수집 및 환경 구성 중...")
    df = get_cached_data(symbol, timeframe)
    
    def update_p(val, txt):
        prog_bar.progress(val, text=txt)
        
    ai_res = run_ai_evolution_search(df, symbol=symbol, timeframe=timeframe, max_iterations=ai_iterations, progress_callback=update_p)
    st.session_state["ai_result"] = ai_res
    st.session_state["last_result"] = ai_res["best_sim"]
    st.session_state["generated_code"] = ai_res["pine_code"]
    prog_bar.empty()
    st.balloons()
    st.success(f"🏆 AI 에이전트가 {ai_res['total_evaluated']}세대의 자율 진화를 완료하고 최적의 Pine Script v6 전략 코드를 합성했습니다!")

# ----------------- [수동 백테스트 모드 로직] -----------------
if btn_manual_run:
    with st.spinner("⏳ 고속 시계열 데이터 로드 및 백테스트 연산 중..."):
        df = get_cached_data(symbol, timeframe)
        params = {
            'st_period': st_period, 'st_mult': st_mult,
            'ema_len': ema_len, 'use_ema_filter': use_ema_filter,
            'min_width_pct': min_width_pct, 'use_min_volat': use_min_volat,
            'tr_ma_len': tr_ma_len, 'use_tr_exit': use_tr_exit,
            'tp_mode': tp_mode, 'sl_mode': sl_mode,
            'tp_fixed_pct': tp_fixed_pct, 'sl_fixed_pct': sl_fixed_pct,
            'tp_atr_mult': tp_atr_mult, 'sl_atr_mult': sl_atr_mult,
            'use_time_exit': use_time_exit, 'max_bars_hold': max_bars_hold
        }
        res = run_simulation(df, params, split_ratio=0.70)
        st.session_state["last_result"] = res
        summary = {
            'symbol': symbol, 'timeframe': timeframe,
            'oos_sharpe': res['oos']['sharpe'], 'oos_return': res['oos']['return_pct'],
            'oos_mdd': res['oos']['mdd'], 'oos_win_rate': res['oos']['win_rate']
        }
        st.session_state["generated_code"] = generate_pine_script_v6(f"Custom {symbol} {timeframe} Strategy v6", params, summary)

# ----------------- [결과 렌더링 섹션] -----------------
if "last_result" in st.session_state:
    res = st.session_state["last_result"]
    is_r = res['is']
    oos_r = res['oos']
    
    # 텔레메트리 메트릭 5종 카드
    c1, c2, c3, c4, c5 = st.columns(5)
    draw_metric(c1, "🏆 OOS 샤프 지수", f"{is_r['sharpe']}", f"{oos_r['sharpe']}", "#007aff" if oos_r['sharpe'] >= 1.0 else "#ff9500")
    draw_metric(c2, "📈 누적 수익률", f"{is_r['return_pct']:+.1f}%", f"{oos_r['return_pct']:+.1f}%", "#34C759" if oos_r['return_pct'] > 0 else "#ff3b30")
    draw_metric(c3, "🛡️ 최대 낙폭 (MDD)", f"{is_r['mdd']:.1f}%", f"{oos_r['mdd']:.1f}%", "#ff3b30" if oos_r['mdd'] > 20 else "#34C759")
    draw_metric(c4, "🎯 승률 (Win Rate)", f"{is_r['win_rate']:.1f}%", f"{oos_r['win_rate']:.1f}%", "#5856d6")
    draw_metric(c5, "🔄 OOS 거래 횟수", f"{is_r['trades_count']}회", f"{oos_r['trades_count']}회", "#ff9500")

    st.divider()
    
    # 에쿼티 커브 차트
    st.subheader("📊 누적 자산 성장 곡선 (Equity Curve: IS vs OOS)")
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.markdown("**In-Sample (과거 70% 학습 구간)**")
        st.line_chart(is_r['equity'], color="#007aff")
    with col_chart2:
        st.markdown("**Out-of-Sample (최근 30% 미지의 검증 구간)**")
        st.line_chart(oos_r['equity'], color="#34C759")

    st.divider()
    
    # 엑셀 다운로드 섹션
    st.subheader("📥 엑셀 상세 리포트 내보내기")
    col_rep1, col_rep2 = st.columns([3, 1])
    with col_rep1:
        st.info("💡 성과 요약 지표와 OOS 구간의 모든 체결 내역(진입가, 청산가, PnL %, 청산사유)이 포함된 엑셀 파일을 생성합니다.")
    with col_rep2:
        excel_path = export_backtest_to_excel(res, symbol=symbol, timeframe=timeframe)
        with open(excel_path, "rb") as f:
            st.download_button("📥 엑셀 리포트 다운로드 (.xlsx)", f, os.path.basename(excel_path), type="primary", use_container_width=True)

    # 📝 AI가 합성한 Pine Script v6 코드 뷰어
    st.divider()
    st.subheader("🤖 AI 에이전트가 자동 합성한 Pine Script v6 전략 코드")
    st.caption("아래 코드는 선택한 차트 시계열에 대해 AI 에이전트가 자율 최적화하여 작성한 완전한 코드입니다. 복사하여 트레이딩뷰에 바로 붙여넣으실 수 있습니다.")
    
    code_text = st.session_state.get("generated_code", "")
    st.text_area("Pine Script Code", value=code_text, height=350)
    
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        st.download_button("💾 파인스크립트 파일 다운로드 (.pine)", code_text, file_name=f"strategy_{symbol.replace('/', '')}_{timeframe}_v6.pine", use_container_width=True)
    with c_btn2:
        if st.button("📋 로컬 strategy_v6.pine 덮어쓰기 저장", use_container_width=True):
            with open("strategy_v6.pine", "w", encoding="utf-8") as f:
                f.write(code_text)
            st.success("✅ 'strategy_v6.pine' 파일로 성공적으로 저장되었습니다!")
else:
    st.info("👈 좌측 사이드바에서 [🤖 AI 자율 분석 및 전략 코드 생성] 버튼을 누르시면, AI 에이전트가 차트를 분석하여 최적의 파인스크립트 코드를 자동으로 합성합니다.")
