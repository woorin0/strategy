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

# 전역 백그라운드 스레드 및 취소 제어 락
_worker_thread = None
_thread_lock = threading.Lock()
_cancel_requested = False

def is_process_running(pid):
    """지정된 PID가 현재 시스템에서 실제로 살아있는지 확인"""
    if pid is None or pid <= 0:
        return False
    try:
        # Windows / Linux 공통 안전 검사
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if process:
                kernel32.CloseHandle(process)
                return True
            return False
        else:
            # POSIX kill -0
            os.kill(pid, 0)
            return True
    except Exception:
        return False

def get_job_status():
    """
    현재 백그라운드 유전 진화 작업 상태 조회
    - 좀비 상태(메모리 부족, 서버 재시작 등으로 스레드가 죽었으나 RUNNING으로 남아있는 경우) 자동 감지하여 INTERRUPTED 전환
    """
    global _worker_thread
    if not os.path.exists(STATUS_FILE):
        return {"status": "IDLE"}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"status": "IDLE"}

    # 상태가 RUNNING인 경우 생존성 검증
    if data.get("status") == "RUNNING":
        now = time.time()
        last_hb = data.get("last_heartbeat", 0)
        task_pid = data.get("pid")
        my_pid = os.getpid()

        # 1. 동일 프로세스 내인데 스레드가 이미 죽어있는 경우
        if task_pid == my_pid:
            if _worker_thread is not None and not _worker_thread.is_alive():
                data["status"] = "INTERRUPTED"
                data["error_message"] = "작업 스레드가 예기치 않게 종료되었습니다."
                update_job_status(data)
                return data

        # 2. 다른 프로세스인데 PID가 죽었거나, 45초 이상 Heartbeat 업데이트가 없는 경우
        if (task_pid and task_pid != my_pid and not is_process_running(task_pid)) or (last_hb > 0 and (now - last_hb) > 45.0):
            data["status"] = "INTERRUPTED"
            data["error_message"] = "서버 재시작 또는 메모리 부족(OOM)으로 인해 작업이 중단되었습니다."
            update_job_status(data)
            return data

    return data

def update_job_status(data):
    """현재 백그라운드 작업 상태 파일 저장"""
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Status Update Error] {e}")

def stop_background_evolution():
    """실행 중인 유전 진화 작업 즉시 강제 중단"""
    global _cancel_requested
    _cancel_requested = True
    job_info = get_job_status()
    if job_info.get("status") == "RUNNING":
        job_info["status"] = "INTERRUPTED"
        job_info["error_message"] = "사용자에 의해 작업이 강제 중단되었습니다."
        update_job_status(job_info)
    return True, "유전 진화 작업 중단 신호를 전송했습니다."

def reset_job_status():
    """멈추거나 실패한 작업 상태를 완전히 클리어하고 IDLE로 리셋"""
    global _cancel_requested, _worker_thread
    _cancel_requested = True
    _worker_thread = None
    idle_info = {
        "status": "IDLE",
        "progress_pct": 0,
        "elapsed_sec": 0,
        "message": "작업 상태가 초기화되었습니다."
    }
    update_job_status(idle_info)
    return True, "작업 상태가 성공적으로 초기화되었습니다."

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
    return {str(k): round(float(v), 2) for k, v in s.items()}

def _evolution_worker_task(symbol, timeframe, max_iterations, min_trades, max_mdd, num_workers, webhook_url, use_discord, df=None, start_date=None):
    """백그라운드 독립 실행 워커 스레드 (초고속 Numba 머신코드 완주 & 안전 모니터링)"""
    global _cancel_requested
    start_time = time.time()
    notified_milestones = set()
    
    # 작업 상태 초기화 (세대당 최대 1,000개 개체군 청크 기준 세대 수 동적 산정)
    pop_size = min(max(max_iterations // 10, 20), 1000)
    calc_total_gen = max(max_iterations // pop_size, 1)
    
    job_info = {
        "status": "RUNNING",
        "pid": os.getpid(),
        "last_heartbeat": time.time(),
        "symbol": symbol,
        "timeframe": timeframe,
        "max_iterations": max_iterations,
        "min_trades": min_trades,
        "max_mdd": max_mdd,
        "workers": num_workers,
        "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "progress_pct": 0,
        "generation": 1,
        "total_generations": calc_total_gen,
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
        job_info["last_heartbeat"] = time.time()
        
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
        # 캔들 데이터 백그라운드 준비 (df가 None이면 비동기 자동 로드)
        if df is None:
            from data_manager import get_cached_data
            job_info["status"] = "RUNNING"
            job_info["last_heartbeat"] = time.time()
            update_job_status(job_info)
            df = get_cached_data(symbol, timeframe, start_date=start_date or "2023-06-01")
            
        # AI 자율 진화 탐색 실행
        ai_res = run_ai_evolution_search(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            max_iterations=max_iterations,
            min_trades=min_trades,
            max_mdd=max_mdd,
            num_workers=num_workers,
            progress_callback=on_progress,
            cancel_check=lambda: _cancel_requested
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
            "raw_trades": best_sim["oos"].get("trades", [])[:100]
        }
        
        # 1) results/latest_strategy.json 저장 (세션 복원용)
        with open(LATEST_STRATEGY_FILE, "w", encoding="utf-8") as f:
            json.dump(strategy_record, f, ensure_ascii=False, indent=2)
            
        # 2) results/strategy_history/ 영구 아카이빙 (.json 및 .pine)
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
        job_info["last_heartbeat"] = time.time()
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
        job_info["status"] = "ERROR" if not _cancel_requested else "INTERRUPTED"
        job_info["error_message"] = str(e)
        job_info["last_heartbeat"] = time.time()
        update_job_status(job_info)

def start_background_evolution(symbol, timeframe, max_iterations, min_trades, max_mdd, num_workers, webhook_url, use_discord, df=None, start_date="2023-06-01"):
    """
    [무중단 백그라운드 유전 진화 작업 시작]
    - 메인 UI를 멈추지 않고 즉시 0.01초 만에 스레드를 띄워 화면 렌더링을 보장
    """
    global _worker_thread, _cancel_requested
    with _thread_lock:
        curr_status = get_job_status()
        if curr_status.get("status") == "RUNNING":
            return False, "이미 백그라운드에서 전략 생성이 가동 중입니다."
            
        _cancel_requested = False
        _worker_thread = threading.Thread(
            target=_evolution_worker_task,
            args=(symbol, timeframe, max_iterations, min_trades, max_mdd, num_workers, webhook_url, use_discord, df, start_date),
            daemon=True
        )
        _worker_thread.start()
        return True, "백그라운드 유전 진화 작업이 시작되었습니다."
