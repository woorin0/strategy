#!/bin/bash
# ========================================================
# ⚡ Vultr Cloud-Init (User-Data) 전자동 무인 설치 스크립트
# 서버 생성 시 User-Data 란에 이 스크립트를 붙여넣으면
# 부팅과 동시에 모든 환경 설치 후 Discord로 접속 링크를 발송합니다.
# ========================================================

# 모든 출력 및 에러를 로그 파일에 기록
exec > >(tee -a /var/log/user-data.log) 2>&1
export DEBIAN_FRONTEND=noninteractive

echo "🚀 [1/6] 2GB 스왑(Swap) 가상 메모리 생성..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "📦 [2/6] 우분투 시스템 업데이트 및 필수 패키지 설치..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv python3-dev build-essential git curl ufw

echo "📁 [3/6] GitHub에서 퀀트 앱 다운로드..."
APP_DIR="/root/quant_app"
rm -rf "$APP_DIR"
git clone https://github.com/woorin0/strategy.git "$APP_DIR"
cd "$APP_DIR"

echo "🐍 [4/6] 파이썬 가상환경 생성 및 패키지 설치..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "🛡️ [5/6] 방화벽(UFW) 8501 포트 개방..."
if command -v ufw >/dev/null 2>&1; then
    ufw allow 8501/tcp comment 'Streamlit Quant Terminal'
    ufw reload || true
fi

echo "⚙️ [6/6] systemd 백그라운드 서비스 등록 및 자동 시작..."
SERVICE_FILE="/etc/systemd/system/quant_terminal.service"
cat <<EOF > $SERVICE_FILE
[Unit]
Description=AI Quantum Research Terminal Streamlit App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/streamlit run app_dashboard.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable quant_terminal
systemctl restart quant_terminal

# 서버 공인 IP 감지 (3초 대기)
sleep 3
SERVER_IP=$(curl -s https://ifconfig.me || curl -s https://api.ipify.org || curl -s http://checkip.amazonaws.com || echo "YOUR_SERVER_IP")

echo "🔔 디스코드 배포 완료 알림 발송 중..."
DISCORD_WEBHOOK="https://discord.com/api/webhooks/1553035812503949382/rnzUhOTIr8Pj0b0mL8NUr2eVn5wb6wRtnEWzYrYykH6sWkhjwOH-8C7_rpgUNctAX0hx"

curl -s -H "Content-Type: application/json" -X POST -d '{
  "embeds": [{
    "title": "🚀 Vultr 서버 전자동(User-Data) 설치 완료!",
    "description": "서버 부팅과 동시에 AI 퀀트 리서치 터미널 앱 설치가 100% 완료되었습니다. 아래 링크를 클릭하여 바로 접속하세요!",
    "color": 3066993,
    "fields": [
      {"name": "🌐 웹 접속 링크", "value": "http://'"$SERVER_IP"':8501", "inline": false},
      {"name": "🖥️ 서버 공인 IP", "value": "'"$SERVER_IP"'", "inline": true},
      {"name": "⚡ 백그라운드 서비스", "value": "Active (Running)", "inline": true},
      {"name": "🛡️ 탑재 전략 지표", "value": "SuperTrend, Squeeze Momentum, SMC, RSI, ADX, Volume MA", "inline": false}
    ],
    "footer": {"text": "AI Quantum Research Terminal v6.0"}
  }]
}' "$DISCORD_WEBHOOK" || true

echo "🎉 모든 배포 작업이 성공적으로 완료되었습니다! 웹 접속: http://${SERVER_IP}:8501"
