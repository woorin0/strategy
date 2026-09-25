import requests
import datetime

DEFAULT_WEBHOOK_URL = "https://discord.com/api/webhooks/1553035812503949382/rnzUhOTIr8Pj0b0mL8NUr2eVn5wb6wRtnEWzYrYykH6sWkhjwOH-8C7_rpgUNctAX0hx"

def send_discord_raw(webhook_url, payload):
    """디스코드 웹훅 전송 기본 함수 (예외 안전 처리)"""
    if not webhook_url:
        webhook_url = DEFAULT_WEBHOOK_URL
    try:
        r = requests.post(webhook_url.strip(), json=payload, timeout=8)
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"[Discord Webhook Error] {e}")
        return False

def send_test_alert(webhook_url=None):
    """디스코드 웹훅 연동 테스트 알림"""
    payload = {
        "embeds": [{
            "title": "⚡ AI Quantum Terminal 연결 성공",
            "description": "디스코드 웹훅 알림 연동이 성공적으로 활성화되었습니다.",
            "color": 3447003, # Blue
            "fields": [
                {"name": "📡 상태", "value": "정상 연결 (Online)", "inline": True},
                {"name": "⏰ 시간", "value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
            ],
            "footer": {"text": "AI Quantum Research Terminal v6.0"}
        }]
    }
    return send_discord_raw(webhook_url, payload)

def send_progress_alert(webhook_url, symbol, timeframe, milestone_pct, current_gen, total_gen, completed, total, best_return, best_win_rate, best_mdd, best_trades, elapsed_sec):
    """유전 진화 진행 상황(25%, 50%, 75%) 마일스톤 웹훅 알림 전송"""
    # 진행 마일스톤에 따른 색상 (25%: 청록 1752220 / 50%: 주황 15105570 / 75%: 보라 10181046)
    colors = {
        25: 1752220,
        50: 15105570,
        75: 10181046
    }
    embed_color = colors.get(milestone_pct, 3447003)
    
    elapsed_str = f"{int(elapsed_sec // 60)}분 {int(elapsed_sec % 60)}초" if elapsed_sec >= 60 else f"{int(elapsed_sec)}초"
    
    fields = [
        {"name": "📊 대상 종목", "value": f"**{symbol}** ({timeframe})", "inline": True},
        {"name": "🧬 진화 세대", "value": f"**{current_gen} / {total_gen} 세대**", "inline": True},
        {"name": "🔄 탐색 진행률", "value": f"**{completed:,} / {total:,} 회 ({milestone_pct}%)**", "inline": True},
        {"name": "💰 현재 최고 수익률", "value": f"**{best_return:+.1f}%**", "inline": True},
        {"name": "🎯 현재 최고 승률", "value": f"**{best_win_rate:.1f}%** ({best_trades}회 거래)", "inline": True},
        {"name": "🛡️ 현재 최고 MDD", "value": f"**{best_mdd:.1f}%**", "inline": True},
        {"name": "⏱️ 경과 시간", "value": f"**{elapsed_str}** 소요 중", "inline": False},
        {"name": "💡 진행 상태 안내", "value": "백그라운드에서 끊김 없이 유전 알고리즘이 가동 중입니다. 브라우저를 닫으셔도 작업은 안전하게 계속됩니다.", "inline": False}
    ]
    
    payload = {
        "embeds": [{
            "title": f"🚀 [AI 퀀트 유전 진화 {milestone_pct}% 달성 보고]",
            "description": f"**{symbol} ({timeframe})** 차트의 다세대 유전 진화 탐색이 **{milestone_pct}%** 구간을 통과했습니다.",
            "color": embed_color,
            "fields": fields,
            "footer": {"text": "AI Quantum Research Terminal v6.0 | Background Worker"}
        }]
    }
    return send_discord_raw(webhook_url, payload)

def send_strategy_alert(webhook_url, mode_name, symbol, timeframe, oos_metrics, is_metrics, params, elapsed_sec=None):
    """전략 코드 생성 100% 완료 시 디스코드로 성과 및 파라미터 상세 리포트 전송"""
    sh = oos_metrics.get('sharpe', 0.0)
    ret = oos_metrics.get('return_pct', 0.0)
    mdd = oos_metrics.get('mdd', 0.0)
    wr = oos_metrics.get('win_rate', 0.0)
    trades = oos_metrics.get('trades_count', 0)
    
    # 성과에 따른 색상 구분 (수익률 1000%+: 골드 15844367 / 양수: 초록 3066993 / 음수: 주황 15105570)
    if ret >= 1000.0:
        embed_color = 15844367
    elif ret > 0:
        embed_color = 3066993
    else:
        embed_color = 15105570
        
    time_info = ""
    if elapsed_sec:
        m, s = divmod(int(elapsed_sec), 60)
        time_info = f" (소요시간: {m}분 {s}초)" if m > 0 else f" (소요시간: {s}초)"
    
    # 활성화된 지표 요약
    indicators_active = []
    indicators_active.append(f"SuperTrend({params.get('st_period')}, {params.get('st_mult')})")
    if params.get('use_squeeze'): indicators_active.append("Squeeze Momentum")
    if params.get('use_smc'): indicators_active.append(f"SMC({params.get('smc_mode')})")
    if params.get('use_rsi'): indicators_active.append(f"RSI({params.get('rsi_mode')})")
    if params.get('use_adx'): indicators_active.append(f"ADX(>={params.get('adx_threshold')})")
    if params.get('use_vol'): indicators_active.append(f"Vol MA({params.get('vol_mult')}x)")
    if params.get('use_ema_filter'): indicators_active.append(f"Macro EMA({params.get('ema_len')})")
    
    fields = [
        {"name": "📊 분석 대상", "value": f"**{symbol}** ({timeframe})", "inline": True},
        {"name": "🎯 OOS 샤프 지수", "value": f"**{sh}**", "inline": True},
        {"name": "💰 OOS 총수익률", "value": f"**{ret:+.1f}%**", "inline": True},
        {"name": "🛡️ 최대 낙폭 (MDD)", "value": f"**{mdd:.1f}%**", "inline": True},
        {"name": "🎲 승률 (Win Rate)", "value": f"**{wr:.1f}%** ({trades}회 거래)", "inline": True},
        {"name": "⚙️ 결합 지표", "value": " + ".join(indicators_active), "inline": False},
        {"name": "📝 파인스크립트 상태", "value": "TradingView Pine Script v6 코드 자동 아카이빙 완료 (대시보드에서 즉시 확인 가능)", "inline": False}
    ]
    
    payload = {
        "embeds": [{
            "title": f"🏆 {mode_name} 전략 코드 생성 완료!{time_info}",
            "description": f"새로운 파인스크립트 v6 퀀트 전략 코드가 생성되었습니다. 대시보드를 열면 코드가 자동으로 복원되어 즉시 확인 및 다운로드하실 수 있습니다.",
            "color": embed_color,
            "fields": fields,
            "footer": {"text": "AI Quantum Research Terminal v6.0"}
        }]
    }
    return send_discord_raw(webhook_url, payload)
