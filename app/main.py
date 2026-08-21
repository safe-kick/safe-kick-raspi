import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from app.routes import lock, session, status
from app.db import init_db
from app.services.safety_service import safety_service




@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    safety_service.start()
    try:
        yield
    finally:
        safety_service.stop()


app = FastAPI(
    title="Safe Kick Raspberry Pi API",
    description="전동 킥보드 안전 인증 시스템 라즈베리파이 서버",
    version="1.1.0",
    lifespan=lifespan,
)

app.include_router(status.router)
app.include_router(session.router)
app.include_router(lock.router)

if os.getenv("ENABLE_FACE_API", "true").lower() == "true":
    from app.routes import face

    app.include_router(face.router)

if os.getenv("ENABLE_TEST_API", "false").lower() == "true":
    from app.routes import test_control

    app.include_router(test_control.router)

@app.get("/")
def root():
    return {
        "status": "success",
        "message": "Safe Kick Raspberry Pi API is running"
    }
