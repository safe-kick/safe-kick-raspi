# 🍓 safe-kick-raspi
Safe Kick - 라즈베리파이 AI 서버  
- FastAPI 기반으로 킥보드 상태 조회, 
- 운행 세션 관리, 
- 실시간 모니터링(SSE),
- 킥보드 잠금/해제, 
- SQLite 로그 저장, 
- STM32 UART 통신을 담당합니다.
---
# 📁 폴더 구조
``` text
safe-kick-raspi/
│
├── app/
│   ├── main.py                  # FastAPI 앱 진입점
│   ├── db.py                    # SQLite 연결 및 테이블 초기화
│   ├── state.py                 # 현재 세션 상태 메모리 관리
│   │
│   ├── routes/
│   │   ├── status.py
│   │   ├── session.py
│   │   └── lock.py
│   │
│   ├── services/
│   │   ├── session_service.py
│   │   ├── lock_service.py
│   │   ├── log_service.py
│   │   └── uart_service.py
│   │
│   ├── managers/
│   │   └── session_manager.py
│   │
│   ├── constants/
│   │   └── uart_commands.py
│   │
│   └── database/
│       └── safe_kick.db
│
├── scripts/
│   └── test_db.py
│
├── requirements.txt
├── .gitignore
└── README.md
```
---
✅ 현재 구현된 API
Status
``` http
GET /status
```
Session
``` http
POST /session/start
GET /session/stream
POST /session/end
GET /session/summary?session_id={id}
```
Lock
``` http
POST /lock
POST /unlock
```
---
🗄 SQLite 테이블
sessions
``` text
id
kickboard_id
user_id
started_at
ended_at
status
warning_count
```
sensor_logs
``` text
id
session_id
face_score
weight
gas
created_at
```
warning_logs
``` text
id
session_id
warning_type
created_at
```
---
🔌 UART 통신
현재 `uart_service.py`는 Mock/Real 전환 구조입니다.
``` env
USE_UART_MOCK=true
SERIAL_PORT=/dev/serial0
BAUD_RATE=115200
```
실제 STM32 연결 시:
``` env
USE_UART_MOCK=false
SERIAL_PORT=/dev/serial0
BAUD_RATE=115200
```
---
▶️ 실행 방법
1. 가상환경 생성
``` bash
python3 -m venv venv
source venv/bin/activate
```
2. 패키지 설치
``` bash
pip install -r requirements.txt
```
3. 서버 실행
``` bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
4. API 문서
``` text
http://라즈베리파이IP:8000/docs
```
---
📡 실시간 모니터링 흐름
``` text
Sensor / Mock Data
        ↓
SessionManager
        ↓
SSE /session/stream
        ↓
React Native Monitoring Screen
```
---
🔜 다음 구현 예정
STM32 UART 실제 연결
MQ-3 알코올 센서 연동
무게 센서 연동
얼굴 인식 모델 연동
Node.js 서버와 운행 종료 요약 연동