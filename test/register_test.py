import base64
import requests
import sys
from pathlib import Path

SERVER = "http://100.115.171.90:8000"
USER_ID = 1

if len(sys.argv) != 2:
    print("사용법:")
    print("python test/register_test.py test/license.jpg")
    exit()

image_path = Path(sys.argv[1])

if not image_path.exists():
    print(f"이미지를 찾을 수 없습니다: {image_path}")
    exit()

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode("utf-8")

res = requests.post(
    f"{SERVER}/face/register",
    json={
        "user_id": USER_ID,
        "image": image_base64,
    }
)

print("Status :", res.status_code)

try:
    print("Response :", res.json())
except Exception:
    print("Response Text :", res.text)
