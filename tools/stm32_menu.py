#!/usr/bin/env python3
"""Interactive numbered menu for standalone STM32 UART testing."""

from __future__ import annotations

import argparse
import os
import threading

import serial


COMMANDS = {
    "0": "CHECK_WEIGHT",
    "1": "STOP_WEIGHT",
    "2": "TEST_MQ3",
    "3": "STOP_TEST_MQ3",
    "4": "CHECK_MQ3",
    "5": "MOTOR_STATE",
    "6": "LOCK",
    "7": "UNLOCK",
    "8": "BUZZ_ON",
    "9": "BUZZ_OFF",
}


def print_menu() -> None:
    print("\n========== STM32 테스트 메뉴 ==========")
    print("0. 무게 측정 시작     CHECK_WEIGHT")
    print("1. 무게 측정 중지     STOP_WEIGHT")
    print("2. MQ3 연속 측정 시작 TEST_MQ3")
    print("3. MQ3 연속 측정 중지 STOP_TEST_MQ3")
    print("4. MQ3 판정 검사       CHECK_MQ3")
    print("5. 모터 상태 확인     MOTOR_STATE")
    print("6. 모터 잠금          LOCK")
    print("7. 모터 잠금 해제     UNLOCK")
    print("8. 부저 켜기          BUZZ_ON")
    print("9. 부저 끄기          BUZZ_OFF")
    print("h. 메뉴 다시 보기")
    print("q. 종료")
    print("=======================================")


def read_serial(port: serial.Serial, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            data = port.readline()
        except serial.SerialException as exc:
            if not stop.is_set():
                print(f"\n[UART 읽기 오류] {exc}")
            return
        if data:
            print(f"\nSTM32 > {data.decode('ascii', errors='replace').strip()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SAFE-KICK STM32 UART test menu")
    parser.add_argument(
        "--port",
        default=os.getenv("SERIAL_PORT", "/dev/serial0"),
        help="STM32 serial device path (default: SERIAL_PORT or /dev/serial0)",
    )
    parser.add_argument(
        "--baud-rate",
        type=int,
        default=int(os.getenv("BAUD_RATE", "115200")),
        help="UART baud rate (default: BAUD_RATE or 115200)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        port = serial.Serial(args.port, args.baud_rate, timeout=0.2)
    except serial.SerialException as exc:
        print(f"UART를 열 수 없습니다: {exc}")
        print("Uvicorn 서버가 실행 중이면 먼저 종료하세요.")
        return 1

    stop = threading.Event()
    reader = threading.Thread(target=read_serial, args=(port, stop), daemon=True)
    reader.start()
    print(f"STM32 연결: {args.port} ({args.baud_rate} baud)")
    print_menu()

    try:
        while True:
            choice = input("\n번호 선택 > ").strip().lower()
            if choice == "q":
                break
            if choice == "h":
                print_menu()
                continue

            command = COMMANDS.get(choice)
            if command is None:
                print("0~9, h 또는 q를 입력하세요.")
                continue

            port.write(f"{command}\r\n".encode("ascii"))
            port.flush()
            print(f"RPi  > {command}")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        stop.set()
        port.close()
        reader.join(timeout=1)

    print("STM32 UART 테스트를 종료했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
