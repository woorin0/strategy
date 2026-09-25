import requests
import datetime

DEFAULT_WEBHOOK_URL = "https://discord.com/api/webhooks/1553035812503949382/rnzUhOTIr8Pj0b0mL8NUr2eVn5wb6wRtnEWzYrYykH6sWkhjwOH-8C7_rpgUNctAX0hx"

def send_discord_raw(webhook_url, payload):
    """디스코드 웹훅 전송 기본 함수 (예외 안전 처리)"""
    if not webhook_url:
        webhook_url = DEFAULT_WEBHOOK_URL
    try:
        r = requests.post(webhook_url.strip(), json=payload, timeout=5)
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

def send_strategy_alert(webhook_url, mode_name, symbol, timeframe, oos_metrics, is_metrics, params, elapsed_sec=None):
    """전략 코드 생성 완료 시 디스코드로 성과 및 파라미터 상세 리포트 전송"""
    sh = oos_metrics.get('sharpe', 0.0)
    ret = oos_metrics.get('return_pct', 0.0)
    mdd = oos_metrics.get('mdd', 0.0)
    wr = oos_metrics.get('win_rate', 0.0)
    trades = oos_metrics.get('trades_count', 0)
    
    # 성과에 따른 색상 구분 (수익률 양수: 초록색 3066993 / 음수: 주황색 15105570)
    embed_color = 3066993 if ret > 0 else 15105570
    
    time_info = f" (소요시간: {elapsed_sec}초)" if elapsed_sec else ""
    
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
        {"name": "💰 OOS 총수익률", "value": f"**{ret}%**", "inline": True},
        {"name": "🛡️ 최대 낙폭 (MDD)", "value": f"**{mdd}%**", "inline": True},
        {"name": "🎲 승률 (Win Rate)", "value": f"**{wr}%** ({trades}회 거래)", "inline": True},
        {"name": "⚙️ 결합 지표", "value": " + ".join(indicators_active), "inline": False},
        {"name": "📝 파인스크립트 상태", "value": "TradingView Pine Script v6 코드 합성 완료 (리페인팅 0%)", "inline": False}
    ]
    
    payload = {
        "embeds": [{
            "title": f"🏆 {mode_name} 전략 코드 생성 완료!{time_info}",
            "description": f"새로운 파인스크립트 v6 퀀트 전략 코드가 생성되었습니다. 대시보드에서 코드를 복사하여 트레이딩뷰에 적용하실 수 있습니다.",
            "color": embed_color,
            "fields": fields,
            "footer": {"text": "AI Quantum Research Terminal v6.0"}
        }]
    }
    return send_discord_raw(webhook_url, payload)
