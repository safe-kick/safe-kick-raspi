#!/usr/bin/env python3
"""Register a license photo and live-verify a helmet photo against a running API."""

from __future__ import annotations

import argparse
import base64
import mimetypes
import sys
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_IMAGE_DIR = PROJECT_ROOT / "test" / "private"


def image_data_url(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"이미지를 찾을 수 없습니다: {path}")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def post_json(server: str, path: str, payload: dict, timeout: float) -> dict:
    response = requests.post(
        f"{server.rstrip('/')}{path}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="면허증 사진을 등록하고 헬멧 착용 사진 한 장을 인증합니다."
    )
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument(
        "--license-image",
        type=Path,
        default=PRIVATE_IMAGE_DIR / "license.jpg",
    )
    parser.add_argument(
        "--helmet-image",
        type=Path,
        default=PRIVATE_IMAGE_DIR / "helmet.jpg",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--start-session",
        action="store_true",
        help="인증 전 테스트 세션을 생성해 STM32 안전 점검 시작 여부도 확인합니다.",
    )
    parser.add_argument("--kickboard-id", default="KB-TEST-001")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.user_id <= 0:
        print("오류: --user-id는 양수여야 합니다.", file=sys.stderr)
        return 2

    try:
        license_image = image_data_url(args.license_image)
        helmet_image = image_data_url(args.helmet_image)

        print(f"[1/3] 면허증 얼굴 등록: {args.license_image}")
        registration = post_json(
            args.server,
            "/face/register",
            {"user_id": args.user_id, "image": license_image},
            args.timeout,
        )
        print(registration)
        if not registration.get("data", {}).get("registered", False):
            print("면허증 얼굴 등록에 실패해 테스트를 중단합니다.", file=sys.stderr)
            return 1

        if args.start_session:
            print("[2/3] 테스트 세션 시작")
            session = post_json(
                args.server,
                "/session/start",
                {"user_id": args.user_id, "kickboard_id": args.kickboard_id},
                args.timeout,
            )
            print(session)
        else:
            print("[2/3] 세션 시작 생략 (safety_check_started는 false일 수 있음)")

        print(f"[3/3] 얼굴 + 헬멧 인증: {args.helmet_image}")
        verification = post_json(
            args.server,
            "/face/live-verify",
            {"user_id": args.user_id, "image": helmet_image},
            args.timeout,
        )
        print(verification)

        data = verification.get("data", {})
        print("\n결과")
        print(f"- 얼굴 인증: {data.get('face_verified')} ({data.get('face_score')})")
        print(f"- 헬멧 인증: {data.get('helmet_verified')} ({data.get('helmet_score')})")
        print(f"- 최종 인증: {data.get('verified')}")
        print(f"- 안전 점검 시작: {data.get('safety_check_started')}")
        return 0 if data.get("verified") else 1
    except FileNotFoundError as error:
        print(f"오류: {error}", file=sys.stderr)
    except requests.RequestException as error:
        print(f"API 요청 실패: {error}", file=sys.stderr)
    except ValueError as error:
        print(f"응답 처리 실패: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
