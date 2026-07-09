import base64
import requests
import sys
from pathlib import Path

SERVER = "http://10.10.141.46:8000"
USER_ID = 1

if len(sys.argv) != 2:
    print("사용법")
    print("python test/verify_test.py test/selfie.jpg")
    exit()

image_path = Path(sys.argv[1])

if not image_path.exists():
    print(f"이미지를 찾을 수 없습니다: {image_path}")
    exit()

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode("utf-8")

response = requests.post(
    f"{SERVER}/face/verify",
    json={
        "user_id": USER_ID,
        "image": image_base64
    }
)

print("Status :", response.status_code)

try:
    print("Response :", response.json())
except Exception:
    print("Response Text :", response.text)