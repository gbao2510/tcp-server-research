import sys
from pathlib import Path

# Đảm bảo import được src và protocol bất kể script chạy từ đâu
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
for d in (str(ROOT_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)
