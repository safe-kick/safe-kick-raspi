# 🍓 safe-kick-raspi

Safe Kick의 **라즈베리파이 AI·센서 서버**입니다.

FastAPI를 기반으로 다음 기능을 담당합니다.

- 킥보드 상태 조회
- 운행 세션 관리
- 실시간 모니터링(SSE)
- 킥보드 잠금·해제
- SQLite 센서 및 경고 로그 저장
- STM32 UART 통신
- 운전면허증 얼굴 등록
- 셀피 얼굴 인증
- 사용자별 얼굴 임베딩 저장

---

# 📁 폴더 구조

```text
safe-kick-raspi/
│
├── app/
│   ├── main.py                       # FastAPI 앱 진입점
│   ├── db.py                         # SQLite 연결 및 테이블 초기화
│   ├── state.py                      # 현재 세션 및 장치 상태 관리
│   │
│   ├── routes/
│   │   ├── status.py                 # 킥보드 현재 상태 조회
│   │   ├── session.py                # 운행 세션 시작·종료·요약·SSE
│   │   ├── lock.py                   # 킥보드 잠금·해제
│   │   └── face.py                   # 면허증 얼굴 등록 및 셀피 인증
│   │
│   ├── services/
│   │   ├── session_service.py        # 운행 세션 처리
│   │   ├── lock_service.py           # 잠금·해제 처리
│   │   ├── log_service.py            # 센서 및 경고 로그 저장
│   │   ├── uart_service.py           # STM32 UART 통신
│   │   └── face_service.py           # InsightFace 얼굴 검출·비교
│   │
│   ├── managers/
│   │   └── session_manager.py        # 세션 상태 및 얼굴 점수 관리
│   │
│   ├── constants/
│   │   └── uart_commands.py          # STM32 UART 명령 상수
│   │
│   └── database/
│       └── safe_kick.db              # SQLite 데이터베이스
│
├── db/
│   └── users/
│       └── {user_id}/
│           └── license_embedding.npy # 사용자별 면허증 얼굴 임베딩
│
├── scripts/
│   └── test_db.py
│
├── requirements.txt
├── .gitignore
└── README.md
```

> 실제 프로젝트에서 라우터 폴더명이 `routers`라면 위 구조의 `routes`를 `routers`로 읽으면 됩니다.

---

# 🧩 시스템 역할

Safe Kick은 프론트엔드, Node.js 백엔드, 라즈베리파이 서버로 역할이 분리되어 있습니다.

```text
React Native 앱
├─ 회원가입·로그인 요청
│      ↓
│  Node.js 백엔드
│  └─ 사용자 계정, 면허 번호, 만료일, JWT 관리
│
└─ 면허증·셀피 이미지 전송
       ↓
   Raspberry Pi FastAPI
   └─ 얼굴 검출, 임베딩 저장, 동일인 비교
```

## 이미지 처리 원칙

- 면허증 원본 이미지는 Node.js 백엔드에 저장하지 않습니다.
- 프론트엔드는 면허증 이미지를 Base64 문자열로 변환하여 Raspberry Pi로 직접 전송합니다.
- Raspberry Pi는 원본 이미지 대신 얼굴 특징값인 임베딩을 저장합니다.
- 사용자별 임베딩은 다음 경로에 저장됩니다.

```text
db/users/{user_id}/license_embedding.npy
```

---

# ✅ 현재 구현된 API

## Status

```http
GET /status
```

현재 세션, 잠금 상태, 경고 상태 등을 조회합니다.

---

## Session

```http
POST /session/start
GET /session/stream
POST /session/end
GET /session/summary?session_id={id}
```

### 주요 기능

- 운행 세션 시작
- 운행 세션 종료
- 현재 센서 상태 SSE 전송
- 운행 요약 조회
- 경고 횟수 및 경고 사유 관리

---

## Lock

```http
POST /lock
POST /unlock
```

### 주요 기능

- 이상 상태 발생 시 킥보드 잠금
- 정상 상태 복구 후 잠금 해제
- 잠금 사유 및 상태 변경
- SSE를 통한 프론트 실시간 반영

---

## Face

### 면허증 얼굴 등록

```http
POST /face/register
```

요청:

```json
{
  "user_id": 1,
  "image": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

처리 과정:

```text
면허증 Base64 이미지 수신
        ↓
OpenCV 이미지 디코딩
        ↓
InsightFace 얼굴 검출
        ↓
가장 큰 얼굴 선택
        ↓
얼굴 임베딩 추출
        ↓
사용자별 .npy 파일 저장
```

등록 성공 응답:

```json
{
  "status": "success",
  "data": {
    "registered": true,
    "user_id": 1,
    "reason": "success"
  },
  "message": "면허증 얼굴 등록이 완료되었습니다."
}
```

얼굴 검출 실패 응답:

```json
{
  "status": "error",
  "data": {
    "registered": false,
    "user_id": 1,
    "reason": "face_not_detected"
  },
  "message": "면허증에서 얼굴을 인식하지 못했습니다."
}
```

잘못된 이미지 응답:

```json
{
  "status": "error",
  "data": {
    "registered": false,
    "user_id": 1,
    "reason": "invalid_image"
  },
  "message": "면허증 이미지가 올바르지 않습니다."
}
```

프론트엔드는 `data.registered`가 `false`이면 로그인을 진행하지 않고 면허증 재촬영 화면으로 이동해야 합니다.

---

### 셀피 얼굴 인증

```http
POST /face/verify
```

요청:

```json
{
  "user_id": 1,
  "image": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

처리 과정:

```text
현재 셀피 이미지 수신
        ↓
셀피 얼굴 임베딩 추출
        ↓
사용자별 면허증 임베딩 로드
        ↓
코사인 유사도 계산
        ↓
임계값 기준 동일인 판정
```

인증 성공 응답:

```json
{
  "status": "success",
  "data": {
    "match": true,
    "confidence": 0.72,
    "face_vector": [],
    "reason": "success"
  },
  "message": "얼굴 인증이 완료되었습니다."
}
```

인증 실패 응답:

```json
{
  "status": "error",
  "data": {
    "match": false,
    "confidence": 0.31,
    "face_vector": [],
    "reason": "not_matched"
  },
  "message": "얼굴 인증에 실패했습니다."
}
```

이미지에서 얼굴을 찾지 못한 경우:

```json
{
  "status": "error",
  "data": {
    "match": false,
    "confidence": 0.0,
    "face_vector": [],
    "reason": "face_not_detected"
  },
  "message": "얼굴 인증에 실패했습니다."
}
```

등록된 사용자 임베딩이 없는 경우:

```json
{
  "status": "error",
  "data": {
    "match": false,
    "confidence": 0.0,
    "face_vector": [],
    "reason": "registered_embedding_not_found"
  },
  "message": "얼굴 인증에 실패했습니다."
}
```

얼굴 인증에 성공하면 유사도 점수가 `SessionManager`에 저장됩니다.

---

# 🤖 얼굴 인식 설정

현재 얼굴 인식 설정은 다음과 같습니다.

```python
FACE_MODEL_NAME = "buffalo_sc"
FACE_PROVIDER = ["CPUExecutionProvider"]
FACE_DET_SIZE = (320, 320)
REGISTERED_MATCH_THRESHOLD = 0.5
```

## 판정 기준

```text
유사도 0.5 이상
→ 동일인 인증 성공

유사도 0.5 미만
→ 동일인 인증 실패
```

## 얼굴이 여러 개 검출된 경우

이미지에서 여러 얼굴이 검출되면 가장 큰 얼굴을 선택합니다.

```python
face = max(
    faces,
    key=lambda f: (
        (f.bbox[2] - f.bbox[0]) *
        (f.bbox[3] - f.bbox[1])
    )
)
```

---

# 🗄 SQLite 테이블

## sessions

```text
id
kickboard_id
user_id
started_at
ended_at
status
warning_count
```

## sensor_logs

```text
id
session_id
face_score
weight
gas
created_at
```

## warning_logs

```text
id
session_id
warning_type
created_at
```

---

# 🔌 UART 통신

`uart_service.py`는 Mock과 실제 STM32 통신을 전환할 수 있는 구조입니다.

## Mock 모드

```env
USE_UART_MOCK=true
SERIAL_PORT=/dev/serial0
BAUD_RATE=115200
```

## 실제 STM32 연결

```env
USE_UART_MOCK=false
SERIAL_PORT=/dev/serial0
BAUD_RATE=115200
```

## 통신 대상

```text
Raspberry Pi
    ↕ UART 115200 8N1
STM32 Nucleo-F411RE
```

STM32는 MQ-3 알코올 센서, 무게 센서, 릴레이, LED, 부저 등의 하드웨어를 제어합니다.

---

# 📡 실시간 모니터링 흐름

```text
STM32 Sensor / Mock Data
        ↓
UART Service
        ↓
SessionManager
        ↓
SQLite 로그 저장
        ↓
SSE /session/stream
        ↓
React Native 모니터링 화면
```

SSE는 다음 상태가 변경될 때 프론트에 실시간 정보를 전달합니다.

- 잠금 상태
- 장치 상태
- 경고 사유
- 2인 탑승 여부
- 음주 감지 여부

---

# 🌐 네트워크 연결

현재 개발 환경에서는 Tailscale을 사용하여 스마트폰, Node.js 서버, Raspberry Pi를 연결할 수 있습니다.

```text
스마트폰
├─ Tailscale → Node.js 백엔드
└─ Tailscale → Raspberry Pi FastAPI
```

프론트엔드 예시:

```ts
export const API_BASE = "http://Node서버-Tailscale-IP";

export const RASPI_IP = "RaspberryPi-Tailscale-IP";
export const RASPI_API_BASE =
  `http://${RASPI_IP}:8000`;
```

핸드폰 IP는 설정하지 않습니다. 핸드폰은 API 요청을 보내는 클라이언트이기 때문입니다.

---

# ▶️ 실행 방법

## 1. 프로젝트 이동

```bash
cd safe-kick-raspi
```

## 2. 가상환경 생성

### Raspberry Pi 또는 Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows 테스트 환경

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

## 3. 패키지 설치

```bash
pip install -r requirements.txt
```

## 4. 서버 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`0.0.0.0`은 모든 네트워크 인터페이스에서 요청을 받기 위한 서버 바인딩 주소입니다.

브라우저 접속 주소로는 사용하지 않습니다.

## 5. API 문서 확인

같은 장치에서 확인:

```text
http://localhost:8000/docs
```

다른 스마트폰 또는 컴퓨터에서 확인:

```text
http://라즈베리파이IP:8000/docs
```

Tailscale 사용 시:

```text
http://라즈베리파이-Tailscale-IP:8000/docs
```

---

# 🧪 얼굴 등록 테스트

Swagger UI에서 다음 API를 선택합니다.

```http
POST /face/register
```

테스트 요청:

```json
{
  "user_id": 1,
  "image": "Base64 이미지 문자열"
}
```

등록 성공 후 파일 확인:

```bash
ls db/users/1
```

예상 결과:

```text
license_embedding.npy
```

---

# 🧪 얼굴 인증 테스트

Swagger UI에서 다음 API를 선택합니다.

```http
POST /face/verify
```

테스트 요청:

```json
{
  "user_id": 1,
  "image": "현재 셀피 Base64 문자열"
}
```

응답의 다음 값을 확인합니다.

```text
data.match
data.confidence
data.reason
```

---

# ⚠️ 주요 실패 사유

| reason | 의미 |
|---|---|
| `success` | 얼굴 등록 또는 인증 성공 |
| `invalid_image` | Base64 이미지 디코딩 실패 |
| `face_not_detected` | 이미지에서 얼굴을 찾지 못함 |
| `not_matched` | 얼굴은 검출됐지만 등록 사용자와 다름 |
| `registered_embedding_not_found` | 해당 사용자의 등록 임베딩 파일이 없음 |

---

# 🔐 개인정보 처리 방향

현재 구조에서는 얼굴 관련 정보를 다음과 같이 처리합니다.

```text
면허증 원본 이미지
→ 프론트에서 Raspberry Pi로 전송
→ 얼굴 임베딩 추출 후 요청 처리 종료

저장 데이터
→ 원본 이미지가 아닌 얼굴 임베딩 파일
```

Node.js 백엔드에는 다음 정보만 저장합니다.

- 사용자 계정
- 이름
- 이메일
- 비밀번호 해시
- 면허 번호
- 면허 만료일

라즈베리파이에는 사용자별 얼굴 임베딩을 저장합니다.

---

# 🔜 다음 구현 및 개선 예정

- STM32 UART 실제 하드웨어 통합 검증
- MQ-3 알코올 센서 측정값 연동
- 무게 센서를 이용한 2인 탑승 감지
- 얼굴 등록 실패 시 프론트 면허증 재촬영 흐름 적용
- 얼굴 인증 실패 횟수 및 재시도 제한
- 사용자 탈퇴 시 얼굴 임베딩 삭제
- 임베딩 파일 암호화 또는 접근 권한 강화
- Node.js 서버와 운행 종료 요약 연동
- 센서 및 얼굴 인증 통합 테스트
