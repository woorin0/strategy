#!/bin/bash
# ==========================================
# ⚡ AI Quantum Research Terminal Vultr One-Click Deployment Script
# ==========================================

set -e

echo "🚀 [1/5] Vultr 리눅스 시스템 패키지 업데이트 및 필수 도구 설치..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv python3-dev build-essential git curl ufw

APP_DIR=$(pwd)
echo "📁 현재 작업 경로: $APP_DIR"

echo "🐍 [2/5] 파이썬 가상환경(venv) 구성..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo "📦 [3/5] 필수 퀀트 패키지 설치 중 (requirements.txt)..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🛡️ [4/5] Vultr 방화벽(UFW) 8501 포트 개방..."
if command -v ufw >/dev/null 2>&1; then
    sudo ufw allow 8501/tcp comment 'Streamlit Quant Terminal'
    sudo ufw reload || true
fi

echo "⚙️ [5/5] systemd 백그라운드 자동 상시 가동 서비스 등록..."
SERVICE_FILE="/etc/systemd/system/quant_terminal.service"

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=AI Quantum Research Terminal Streamlit App
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/streamlit run app_dashboard.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable quant_terminal
sudo systemctl restart quant_terminal

# 서버 공인 IP 감지
SERVER_IP=$(curl -s https://ifconfig.me || curl -s https://api.ipify.org || echo "YOUR_SERVER_IP")

echo ""
echo "=========================================================="
echo "🎉 배포가 완벽하게 완료되었습니다!"
echo "🌐 웹 브라우저에서 아래 주소로 즉시 접속하실 수 있습니다:"
echo ""
echo "   👉 http://${SERVER_IP}:8501"
echo ""
echo "📌 서비스 상태 확인: sudo systemctl status quant_terminal"
echo "📌 서비스 재시작:   sudo systemctl restart quant_terminal"
echo "📌 로그 실시간 확인: sudo journalctl -u quant_terminal -f"
echo "=========================================================="
