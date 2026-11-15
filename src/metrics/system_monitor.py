"""Module giám sát tài nguyên hệ thống (CPU).
Chức năng:
- Thu thập phần trăm sử dụng CPU (% CPU usage) theo chu kỳ định trước bằng daemon thread.
- Ưu tiên sử dụng thư viện `psutil` nếu có.
- Nếu không có `psutil`, tự động kích hoạt Windows Native Kernel32 API (qua thư viện chuẩn `ctypes`)
  giúp đo CPU chính xác 100% trên Windows mà không cần cài thêm bất kỳ gói nào.
"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from typing import Any

# 1. Thử import psutil
_PSUTIL_AVAILABLE = False
try:
    import psutil  # type: ignore
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None

# 2. Chuẩn bị Native Windows API qua ctypes nếu chạy trên Windows
_WIN32_AVAILABLE = False
if os.name == "nt":
    try:
        class _FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint), ("dwHighDateTime", ctypes.c_uint)]

        def _ft_to_int(ft: _FILETIME) -> int:
            return (ft.dwHighDateTime << 32) + ft.dwLowDateTime

        _kernel32 = ctypes.windll.kernel32
        _GetSystemTimes = _kernel32.GetSystemTimes
        _WIN32_AVAILABLE = True
    except Exception:
        _WIN32_AVAILABLE = False


def _get_win32_system_times() -> tuple[int, int, int]:
    idle = _FILETIME()
    kernel = _FILETIME()
    user = _FILETIME()
    _GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    return _ft_to_int(idle), _ft_to_int(kernel), _ft_to_int(user)


class CpuMonitor:
    """Theo dõi mức sử dụng CPU trong quá trình chạy benchmark."""

    def __init__(
        self,
        interval: float = 0.2,
        target_pid: int | None = None,
    ) -> None:
        """
        :param interval: Khoảng thời gian lấy mẫu CPU (giây).
        :param target_pid: PID của process cần theo dõi (chỉ áp dụng khi có psutil).
        """
        self.interval = interval
        self.target_pid = target_pid
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.samples: list[float] = []
        self.timestamps: list[float] = []
        self._start_time: float = 0.0

    @property
    def is_available(self) -> bool:
        return _PSUTIL_AVAILABLE or _WIN32_AVAILABLE

    @property
    def backend_name(self) -> str:
        if _PSUTIL_AVAILABLE:
            return "psutil"
        if _WIN32_AVAILABLE:
            return "windows_kernel32"
        return "none"

    def _sample_loop(self) -> None:
        # Trường hợp 1: Dùng psutil
        if _PSUTIL_AVAILABLE:
            process = None
            if self.target_pid:
                try:
                    process = psutil.Process(self.target_pid)
                    process.cpu_percent(interval=None)
                except Exception:
                    process = None
            psutil.cpu_percent(interval=None)

            while not self._stop_event.is_set():
                time.sleep(self.interval)
                if self._stop_event.is_set():
                    break
                now = time.monotonic() - self._start_time
                cpu_val = 0.0
                try:
                    if process and process.is_running():
                        cpu_val = process.cpu_percent(interval=None)
                    else:
                        cpu_val = psutil.cpu_percent(interval=None)
                except Exception:
                    cpu_val = 0.0
                self.timestamps.append(now)
                self.samples.append(cpu_val)
            return

        # Trường hợp 2: Dùng Windows Native API qua ctypes (GetSystemTimes)
        if _WIN32_AVAILABLE:
            prev_idle, prev_kernel, prev_user = _get_win32_system_times()
            while not self._stop_event.is_set():
                time.sleep(self.interval)
                if self._stop_event.is_set():
                    break
                now = time.monotonic() - self._start_time
                cur_idle, cur_kernel, cur_user = _get_win32_system_times()

                sys_diff = (cur_kernel - prev_kernel) + (cur_user - prev_user)
                idle_diff = cur_idle - prev_idle

                if sys_diff > 0:
                    cpu_pct = (sys_diff - idle_diff) / sys_diff * 100.0
                    cpu_pct = max(0.0, min(100.0, cpu_pct))
                else:
                    cpu_pct = 0.0

                self.timestamps.append(now)
                self.samples.append(round(cpu_pct, 2))
                prev_idle, prev_kernel, prev_user = cur_idle, cur_kernel, cur_user
            return

        # Trường hợp 3: Không có backend nào
        while not self._stop_event.is_set():
            time.sleep(self.interval)

    def start(self) -> CpuMonitor:
        """Bắt đầu thread lấy mẫu CPU."""
        if not self.is_available:
            logging.warning("Không có backend giám sát CPU nào khả dụng, chỉ số CPU sẽ trả về 0.0%%")

        self.samples.clear()
        self.timestamps.clear()
        self._stop_event.clear()
        self._start_time = time.monotonic()

        self._thread = threading.Thread(target=self._sample_loop, daemon=True, name="CpuMonitorThread")
        self._thread.start()
        return self

    def stop(self) -> dict[str, Any]:
        """Dừng lấy mẫu và trả về bản tóm tắt thông số CPU."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        return self.summary()

    def summary(self) -> dict[str, Any]:
        """Thống kê CPU trung bình, nhỏ nhất, lớn nhất."""
        if not self.samples:
            return {
                "available": self.is_available,
                "backend": self.backend_name,
                "samples_count": 0,
                "cpu_avg": 0.0,
                "cpu_min": 0.0,
                "cpu_max": 0.0,
            }

        return {
            "available": True,
            "backend": self.backend_name,
            "samples_count": len(self.samples),
            "cpu_avg": round(sum(self.samples) / len(self.samples), 2),
            "cpu_min": round(min(self.samples), 2),
            "cpu_max": round(max(self.samples), 2),
        }

    def __enter__(self) -> CpuMonitor:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
