import os
import json
import time
import threading
import datetime
import pandas as pd
from ai_generator import run_ai_evolution_search
from discord_notifier import send_progress_alert, send_strategy_alert, DEFAULT_WEBHOOK_URL

RESULTS_DIR = os.path.join(os.getcwd(), "results")
HISTORY_DIR = os.path.join(RESULTS_DIR, "strategy_history")
STATUS_FILE = os.path.join(RESULTS_DIR, "evolution_job.json")
LATEST_STRATEGY_FILE = os.path.join(RESULTS_DIR, "latest_strategy.json")

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# 전역 백그라운드 스레드 락 및 상태
_worker_thread = None
_thread_lock = threading.Lock()

def get_job_status():
    """현재 백그라운드 유전 진화 작업 상태 조회"""
    if not os.path.exists(STATUS_FILE):
        return {"status": "IDLE"}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"status": "IDLE"}

def update_job_status(data):
    """현재 백그라운드 작업 상태 파일 저장"""
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Status Update Error] {e}")

def get_latest_strategy():
    """가장 최근에 완료된 전략 결과 및 코드 로드 (자동 복원용)"""
    if not os.path.exists(LATEST_STRATEGY_FILE):
        return None
    try:
        with open(LATEST_STRATEGY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Load Latest Strategy Error] {e}")
        return None

def list_strategy_history():
    """과거 생성된 모든 전략 히스토리 목록 조회"""
    if not os.path.exists(HISTORY_DIR):
        return []
    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")]
    files.sort(reverse=True)
    history_items = []
    for f in files:
        filepath = os.path.join(HISTORY_DIR, f)
        try:
            with open(filepath, "r", encoding="utf-8") as jf:
                data = json.load(jf)
                history_items.append({
                    "filename": f,
                    "filepath": filepath,
                    "symbol": data.get("symbol", "N/A"),
                    "timeframe": data.get("timeframe", "N/A"),
                    "return_pct": data.get("oos_return", 0.0),
                    "win_rate": data.get("oos_win_rate", 0.0),
                    "mdd": data.get("oos_mdd", 0.0),
                    "timestamp": data.get("created_at", f.replace("strategy_", "").replace(".json", ""))
                })
        except Exception:
            continue
    return history_items

def load_strategy_history(filepath):
    """특정 과거 전략 상세 데이터 로드"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _downsample_equity_for_storage(equity_series, max_pts=500):
    """에쿼티 커브 저장 시 브라우저 랙 방지를 위해 경량화"""
    if equity_series is None or len(equity_series) == 0:
        return {}
    if isinstance(equity_series, pd.Series):
        s = equity_series
    else:
        s = pd.Series(equity_series)
    if len(s) > max_pts:
        step = max(1, len(s) // max_pts)
        s = s.iloc[::step].copy()
    # str(index) -> float 변환
    return {str(k): round(float(v), 2) for k, v in s.items()}

def _evolution_worker_task(df, symbol, timeframe, max_iterations, min_trades, max_mdd, num_workers, webhook_url, use_discord):
    """백그라운드 독립 실행 워커 스레드 (브라우저가 꺼져도 서버에서 100% 완주)"""
    start_time = time.time()
    notified_milestones = set()
    
    # 작업 상태 초기화
    job_info = {
        "status": "RUNNING",
        "symbol": symbol,
        "timeframe": timeframe,
        "max_iterations": max_iterations,
        "min_trades": min_trades,
        "max_mdd": max_mdd,
        "workers": num_workers,
        "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "progress_pct": 0,
        "generation": 1,
        "total_generations": 5 if max_iterations >= 3000 else 4 if max_iterations >= 1000 else 3 if max_iterations >= 200 else 2,
        "completed": 0,
        "total": max_iterations,
        "best_return": 0.0,
        "best_win_rate": 0.0,
        "best_mdd": 0.0,
        "best_trades": 0,
        "elapsed_sec": 0,
        "notified_milestones": []
    }
    update_job_status(job_info)
    
    def on_progress(pct, msg):
        elapsed = time.time() - start_time
        job_info["progress_pct"] = pct
        job_info["elapsed_sec"] = round(elapsed, 1)
        
        # 메시지에서 세대 및 최고 성과 파싱 보정
        try:
            if "세대]" in msg:
                gen_part = msg.split("세대]")[0].split("진화")[1].strip()
                curr_g, tot_g = gen_part.split("/")
                job_info["generation"] = int(curr_g)
                job_info["total_generations"] = int(tot_g)
            if "최고 수익률:" in msg:
                ret_str = msg.split("최고 수익률:")[1].split("%")[0].strip()
                job_info["best_return"] = float(ret_str)
            if "승률:" in msg:
                wr_str = msg.split("승률:")[1].split("%")[0].strip()
                job_info["best_win_rate"] = float(wr_str)
            if "MDD:" in msg:
                mdd_str = msg.split("MDD:")[1].split("%")[0].strip()
                job_info["best_mdd"] = float(mdd_str)
            if "거래:" in msg:
                tr_str = msg.split("거래:")[1].split("회")[0].strip()
                job_info["best_trades"] = int(tr_str)
        except Exception:
            pass
            
        update_job_status(job_info)
        
        # 🔔 25%, 50%, 75% 마일스톤 웹훅 알림 전송 (중복 방지)
        for milestone in [25, 50, 75]:
            if pct >= milestone and milestone not in notified_milestones:
                notified_milestones.add(milestone)
                job_info["notified_milestones"].append(milestone)
                update_job_status(job_info)
                if use_discord and webhook_url:
                    send_progress_alert(
                        webhook_url=webhook_url,
                        symbol=symbol,
                        timeframe=timeframe,
                        milestone_pct=milestone,
                        current_gen=job_info["generation"],
                        total_gen=job_info["total_generations"],
                        completed=int((pct / 100.0) * max_iterations),
                        total=max_iterations,
                        best_return=job_info["best_return"],
                        best_win_rate=job_info["best_win_rate"],
                        best_mdd=job_info["best_mdd"],
                        best_trades=job_info["best_trades"],
                        elapsed_sec=elapsed
                    )
    
    try:
        # AI 자율 진화 탐색 실행
        ai_res = run_ai_evolution_search(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            max_iterations=max_iterations,
            min_trades=min_trades,
            max_mdd=max_mdd,
            num_workers=num_workers,
            progress_callback=on_progress
        )
        
        elapsed_sec = round(time.time() - start_time, 2)
        best_sim = ai_res["best_sim"]
        best_params = ai_res["best_params"]
        pine_code = ai_res["pine_code"]
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_sym = symbol.replace("/", "")
        
        # 영구 저장용 전략 데이터 객체 생성
        strategy_record = {
            "symbol": symbol,
            "timeframe": timeframe,
            "created_at": now_str,
            "elapsed_sec": elapsed_sec,
            "max_iterations": max_iterations,
            "min_trades": min_trades,
            "max_mdd": max_mdd,
            "workers_used": ai_res["workers_used"],
            "generations": ai_res.get("generations", 5),
            "oos_sharpe": best_sim["oos"]["sharpe"],
            "oos_return": best_sim["oos"]["return_pct"],
            "oos_mdd": best_sim["oos"]["mdd"],
            "oos_win_rate": best_sim["oos"]["win_rate"],
            "oos_trades": best_sim["oos"]["trades_count"],
            "is_sharpe": best_sim["is"]["sharpe"],
            "is_return": best_sim["is"]["return_pct"],
            "is_mdd": best_sim["is"]["mdd"],
            "is_win_rate": best_sim["is"]["win_rate"],
            "is_trades": best_sim["is"]["trades_count"],
            "overfitting_ratio": best_sim.get("overfitting_ratio", 1.0),
            "best_params": best_params,
            "pine_code": pine_code,
            "oos_equity": _downsample_equity_for_storage(best_sim["oos"].get("equity")),
            "is_equity": _downsample_equity_for_storage(best_sim["is"].get("equity")),
            "raw_trades": best_sim["oos"].get("trades", [])[:100] # 최근 100개 거래 기록
        }
        
        # 1) results/latest_strategy.json 에 저장 (세션 복원용)
        with open(LATEST_STRATEGY_FILE, "w", encoding="utf-8") as f:
            json.dump(strategy_record, f, ensure_ascii=False, indent=2)
            
        # 2) results/strategy_history/ 폴더에 영구 아카이빙 (.json 및 .pine)
        hist_json = os.path.join(HISTORY_DIR, f"strategy_{clean_sym}_{timeframe}_{time_tag}.json")
        with open(hist_json, "w", encoding="utf-8") as f:
            json.dump(strategy_record, f, ensure_ascii=False, indent=2)
            
        hist_pine = os.path.join(HISTORY_DIR, f"strategy_{clean_sym}_{timeframe}_{time_tag}.pine")
        with open(hist_pine, "w", encoding="utf-8") as f:
            f.write(pine_code)
            
        # 3) 루트의 strategy_v6.pine 자동 동기화
        root_pine = os.path.join(os.getcwd(), "strategy_v6.pine")
        with open(root_pine, "w", encoding="utf-8") as f:
            f.write(pine_code)
            
        # 4) 작업 상태를 COMPLETED로 전환
        job_info["status"] = "COMPLETED"
        job_info["progress_pct"] = 100
        job_info["completed"] = max_iterations
        job_info["elapsed_sec"] = elapsed_sec
        job_info["best_return"] = best_sim["oos"]["return_pct"]
        job_info["best_win_rate"] = best_sim["oos"]["win_rate"]
        job_info["best_mdd"] = best_sim["oos"]["mdd"]
        job_info["best_trades"] = best_sim["oos"]["trades_count"]
        update_job_status(job_info)
        
        # 5) 🔔 100% 완료 디스코드 웹훅 발송
        if use_discord and webhook_url:
            send_strategy_alert(
                webhook_url=webhook_url,
                mode_name="🤖 AI 자율 진화 (100% 완료)",
                symbol=symbol,
                timeframe=timeframe,
                oos_metrics=best_sim["oos"],
                is_metrics=best_sim["is"],
                params=best_params,
                elapsed_sec=elapsed_sec
            )
            
    except Exception as e:
        print(f"[Evolution Task Error] {e}")
        job_info["status"] = "ERROR"
        job_info["error_message"] = str(e)
        update_job_status(job_info)

def start_background_evolution(df, symbol, timeframe, max_iterations, min_trades, max_mdd, num_workers, webhook_url, use_discord):
    """
    [핵심: 무중단 백그라운드 작업 시작]
    Streamlit 세션에 종속되지 않는 독립 데몬 스레드로 실행
    """
    global _worker_thread
    with _thread_lock:
        curr_status = get_job_status()
        if curr_status.get("status") == "RUNNING":
            return False, "이미 백그라운드에서 전략 생성이 가동 중입니다."
            
        _worker_thread = threading.Thread(
            target=_evolution_worker_task,
            args=(df, symbol, timeframe, max_iterations, min_trades, max_mdd, num_workers, webhook_url, use_discord),
            daemon=True
        )
        _worker_thread.start()
        return True, "백그라운드 유전 진화 작업이 시작되었습니다."
