import base64
import sys
from pathlib import Path

# =========================
# 사용법
# python image_to_base64.py license.png
# =========================

if len(sys.argv) != 2:
    print("사용법:")
    print("python image_to_base64.py <이미지>")
    exit()

image_path = Path(sys.argv[1])

if not image_path.exists():
    print("이미지를 찾을 수 없습니다.")
    exit()

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode("utf-8")

print("=" * 80)
print(image_base64)
print("=" * 80)

print()
print("길이 :", len(image_base64))