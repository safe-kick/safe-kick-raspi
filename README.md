# 🍓 safe-kick-raspi
Safe Kick - 라즈베리파이 AI 서버 (FastAPI + InsightFace)

## 📁 폴더 구조

```
safe-kick-raspi/
│
├── main.py                     # FastAPI 앱 진입점
│
├── routers/                    # API 라우터
│   ├── status.py               # GET /status
│   ├── session.py              # POST /session/start, /session/end, GET /session/stream, /session/summary
│   └── lock.py                 # POST /lock, /unlock
│
├── services/                   # 핵심 비즈니스 로직
│   ├── face.py                 # InsightFace 얼굴 인식 및 벡터 비교
│   ├── uart.py                 # pyserial STM32 UART 통신
│   └── sensor.py               # 센서값 판단 (음주 / 2인 탑승)
│
├── db/                         # SQLite 연결 및 쿼리
│   └── database.py
│
├── models/                     # DB 테이블 모델
│   └── schema.py               # kickboard, session, sensor_log, lock_log
│
├── requirements.txt
└── README.md
```
