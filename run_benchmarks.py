"""Shortcut chạy thực nghiệm tự động các mức Client (1, 10, 50) và xuất dữ liệu thô (CSV/JSON).
Tác giả: Trần Trung Trực (Metrics & Test Script Dev).

Cách dùng:
    python run_benchmarks.py
    python run_benchmarks.py --requests 50 --host 127.0.0.1 --port 9000
"""
from __future__ import annotations

import sys
from pathlib import Path

# Đảm bảo đường dẫn import
ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "experiments" / "scripts"
for d in (str(ROOT_DIR), str(SCRIPTS_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from experiments.scripts.run_benchmarks import main

if __name__ == "__main__":
    raise SystemExit(main())
