import os
import time
from app.constants.uart_commands import UARTCommand

USE_UART_MOCK = os.getenv("USE_UART_MOCK", "true").lower() == "true"

SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/serial0")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))


class UARTService:
    def __init__(self):
        self.ser = None

    def connect(self):
        if USE_UART_MOCK:
            return

        import serial

        if self.ser is None or not self.ser.is_open:
            self.ser = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                timeout=1
            )
            time.sleep(2)

    def send_command(self, command: str):
        if USE_UART_MOCK:
            return self._mock_response(command)

        self.connect()

        message = command.strip() + "\n"
        self.ser.write(message.encode("utf-8"))

        response = self.ser.readline().decode("utf-8").strip()
        return response

    def _mock_response(self, command: str):
        command = command.strip()

        if command == UARTCommand.PING:
            return "PONG"

        if command == UARTCommand.LOCK:
            return "ACK:LOCK"

        if command == UARTCommand.UNLOCK:
            return "ACK:UNLOCK"

        if command == UARTCommand.REQUEST_MQ3:
            return "RES:MQ3:0.12"

        if command == UARTCommand.REQUEST_WEIGHT:
            return "RES:WEIGHT:65.3"

        return "ERR:UNKNOWN_COMMAND"

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()


uart_service = UARTService()