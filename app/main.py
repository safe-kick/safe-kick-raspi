from fastapi import FastAPI
from app.routes import status, session, lock
from app.db import init_db




init_db()


app = FastAPI(
    title="Safe Kick Raspberry Pi API",
    description="전동 킥보드 안전 인증 시스템 라즈베리파이 서버",
    version="1.0.0"
)

app.include_router(status.router)
app.include_router(session.router)
app.include_router(lock.router)

@app.get("/")
def root():
    return {
        "status": "success",
        "message": "Safe Kick Raspberry Pi API is running"
    }