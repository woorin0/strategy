import pandas as pd
import os
import datetime

REPORTS_DIR = "results"

def export_backtest_to_excel(summary_dict, symbol="BTCUSDT", timeframe="1h"):
    """백테스트 요약 및 거래 내역을 엑셀(.xlsx) 파일로 내보내기"""
    if not os.path.exists(REPORTS_DIR):
        os.makedirs(REPORTS_DIR)
        
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_sym = symbol.replace("/", "")
    filename = f"report_{clean_sym}_{timeframe}_{now_str}.xlsx"
    filepath = os.path.join(REPORTS_DIR, filename)
    
    # 1. 요약 데이터프레임
    summary_data = [
        {"지표": "분석 심볼 / 타임프레임", "In-Sample (70%)": f"{symbol} ({timeframe})", "Out-of-Sample (30%)": f"{symbol} ({timeframe})"},
        {"지표": "총 거래 횟수", "In-Sample (70%)": summary_dict['is']['trades_count'], "Out-of-Sample (30%)": summary_dict['oos']['trades_count']},
        {"지표": "샤프 지수 (Sharpe Ratio)", "In-Sample (70%)": summary_dict['is']['sharpe'], "Out-of-Sample (30%)": summary_dict['oos']['sharpe']},
        {"지표": "최대 낙폭 (MDD)", "In-Sample (70%)": f"{summary_dict['is']['mdd']}%", "Out-of-Sample (30%)": f"{summary_dict['oos']['mdd']}%"},
        {"지표": "승률 (Win Rate)", "In-Sample (70%)": f"{summary_dict['is']['win_rate']}%", "Out-of-Sample (30%)": f"{summary_dict['oos']['win_rate']}%"},
        {"지표": "총 누적 수익률", "In-Sample (70%)": f"{summary_dict['is']['return_pct']}%", "Out-of-Sample (30%)": f"{summary_dict['oos']['return_pct']}%"},
        {"지표": "과적합 방어 지수 (OOS/IS)", "In-Sample (70%)": "-", "Out-of-Sample (30%)": summary_dict['overfitting_ratio']}
    ]
    df_summary = pd.DataFrame(summary_data)
    
    # 2. 거래 내역 데이터프레임 (OOS)
    oos_trades = summary_dict['oos'].get('trades', [])
    df_trades_oos = pd.DataFrame(oos_trades) if oos_trades else pd.DataFrame(columns=['진입시간', '청산시간', '유형', '진입가', '청산가', '수익률(%)', '청산사유'])
    
    # 3. 엑셀 작성
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='성과 요약', index=False)
        if not df_trades_oos.empty:
            df_trades_oos.to_excel(writer, sheet_name='OOS 거래 내역', index=False)
            
    return filepath
