"""Unit Tests cho Module Đo lường (Metrics Module) - Metrics Dev.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
for d in (str(ROOT_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from src.metrics import (
    CpuMonitor,
    MetricsCollector,
    Sample,
    calculate_percentile,
    export_all_raw_data,
    format_summary,
    read_csv,
    read_json,
    summarize,
    write_cpu_csv,
    write_cpu_json,
    write_csv,
    write_json,
)


class TestCalculatePercentile(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(calculate_percentile([], 95), 0.0)

    def test_single_element(self):
        self.assertEqual(calculate_percentile([42.5], 95), 42.5)

    def test_percentile_1_to_100(self):
        data = list(range(1, 101))  # 1 .. 100
        p95 = calculate_percentile(data, 95.0)
        self.assertAlmostEqual(p95, 95.05, places=2)
        p50 = calculate_percentile(data, 50.0)
        self.assertAlmostEqual(p50, 50.5, places=2)


class TestSummarize(unittest.TestCase):
    def test_all_ok(self):
        samples = [
            Sample(client_id=0, seq=0, t_start=0.1, latency_ms=10.0, ok=True),
            Sample(client_id=0, seq=1, t_start=0.2, latency_ms=20.0, ok=True),
            Sample(client_id=0, seq=2, t_start=0.3, latency_ms=30.0, ok=True),
        ]
        s = summarize(samples, elapsed_s=1.0)
        self.assertEqual(s["total_requests"], 3)
        self.assertEqual(s["requests_ok"], 3)
        self.assertEqual(s["requests_failed"], 0)
        self.assertEqual(s["throughput_rps"], 3.0)
        self.assertAlmostEqual(s["latency_avg_ms"], 20.0)
        self.assertEqual(s["latency_min_ms"], 10.0)
        self.assertEqual(s["latency_max_ms"], 30.0)

    def test_with_failures(self):
        samples = [
            Sample(client_id=0, seq=0, t_start=0.1, latency_ms=10.0, ok=True),
            Sample(client_id=0, seq=1, t_start=0.2, latency_ms=100.0, ok=False, error="timeout"),
            Sample(client_id=0, seq=2, t_start=0.3, latency_ms=20.0, ok=True),
        ]
        s = summarize(samples, elapsed_s=1.0)
        self.assertEqual(s["total_requests"], 3)
        self.assertEqual(s["requests_ok"], 2)
        self.assertEqual(s["requests_failed"], 1)
        self.assertEqual(s["throughput_rps"], 2.0)
        # Latency chỉ tính trên các request OK
        self.assertAlmostEqual(s["latency_avg_ms"], 15.0)
        self.assertEqual(s["errors"], {"timeout": 1})

    def test_warmup_filtering(self):
        samples = [
            Sample(client_id=0, seq=0, t_start=0.5, latency_ms=100.0, ok=True),  # warmup
            Sample(client_id=0, seq=1, t_start=1.2, latency_ms=10.0, ok=True),
            Sample(client_id=0, seq=2, t_start=1.5, latency_ms=20.0, ok=True),
        ]
        s = summarize(samples, elapsed_s=2.0, warmup_s=1.0)
        self.assertEqual(s["total_requests"], 2)
        self.assertEqual(s["requests_ok"], 2)
        self.assertAlmostEqual(s["latency_avg_ms"], 15.0)


class TestCSVExport(unittest.TestCase):
    def test_csv_roundtrip(self):
        samples = [
            Sample(client_id=1, seq=0, t_start=0.012345, latency_ms=5.4321, ok=True, error=""),
            Sample(client_id=1, seq=1, t_start=0.065432, latency_ms=50.1234, ok=False, error="timeout"),
        ]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            write_csv(samples, tmp_path)
            loaded = read_csv(tmp_path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].client_id, 1)
            self.assertEqual(loaded[0].seq, 0)
            self.assertTrue(loaded[0].ok)
            self.assertAlmostEqual(loaded[0].latency_ms, 5.4321, places=3)
            self.assertFalse(loaded[1].ok)
            self.assertEqual(loaded[1].error, "timeout")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestMetricsCollector(unittest.TestCase):
    def test_multithread_collector(self):
        collector = MetricsCollector()

        def worker(cid: int):
            for i in range(50):
                collector.record(client_id=cid, seq=i, t_start=0.01 * i, latency_ms=1.5, ok=True)

        threads = [threading.Thread(target=worker, args=(c,)) for c in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        samples = collector.get_samples()
        self.assertEqual(len(samples), 250)
        summary = collector.summarize(elapsed_s=1.0)
        self.assertEqual(summary["requests_ok"], 250)


class TestCpuMonitor(unittest.TestCase):
    def test_monitor_lifecycle(self):
        monitor = CpuMonitor(interval=0.05)
        monitor.start()
        time.sleep(0.15)
        res = monitor.stop()
        self.assertIn("cpu_avg", res)
        self.assertIn("cpu_min", res)
        self.assertIn("cpu_max", res)


class TestJSONExport(unittest.TestCase):
    """Kiểm thử tính năng xuất và đọc dữ liệu thô dạng JSON (Trần Trung Trực - Metrics Dev)."""

    def test_json_roundtrip(self):
        samples = [
            Sample(client_id=1, seq=0, t_start=0.012345, latency_ms=5.4321, ok=True, error=""),
            Sample(client_id=1, seq=1, t_start=0.065432, latency_ms=50.1234, ok=False, error="timeout"),
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            write_json(samples, tmp_path)
            loaded = read_json(tmp_path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].client_id, 1)
            self.assertEqual(loaded[0].seq, 0)
            self.assertTrue(loaded[0].ok)
            self.assertAlmostEqual(loaded[0].latency_ms, 5.4321, places=3)
            self.assertFalse(loaded[1].ok)
            self.assertEqual(loaded[1].error, "timeout")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestCPUExport(unittest.TestCase):
    """Kiểm thử tính năng xuất dữ liệu thô CPU ra CSV và JSON (Trần Trung Trực - Metrics Dev)."""

    def test_cpu_csv_export(self):
        timestamps = [0.1, 0.2, 0.3]
        cpu_values = [15.5, 20.0, 18.2]
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            write_cpu_csv(tmp_path, timestamps=timestamps, cpu_percent=cpu_values)
            self.assertTrue(tmp_path.exists())
            with open(tmp_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("timestamp_s,cpu_percent", content)
            self.assertIn("0.1000,15.50", content)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_cpu_json_export(self):
        timestamps = [0.1, 0.2]
        cpu_values = [10.0, 30.0]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            write_cpu_json(tmp_path, timestamps=timestamps, cpu_percent=cpu_values)
            self.assertTrue(tmp_path.exists())
            import json
            with open(tmp_path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("summary", data)
            self.assertIn("samples", data)
            self.assertEqual(data["summary"]["cpu_avg"], 20.0)
            self.assertEqual(len(data["samples"]), 2)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_cpu_monitor_save_methods(self):
        monitor = CpuMonitor(interval=0.05)
        monitor.start()
        time.sleep(0.12)
        monitor.stop()

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "cpu_test.csv"
            json_path = Path(tmp_dir) / "cpu_test.json"
            monitor.save_csv(csv_path)
            monitor.save_json(json_path)
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())


class TestExportAllRawData(unittest.TestCase):
    """Kiểm thử tính năng xuất trọn bộ dữ liệu thô (Trần Trung Trực - Metrics Dev)."""

    def test_export_all(self):
        samples = [
            Sample(client_id=1, seq=0, t_start=0.01, latency_ms=4.2, ok=True),
        ]
        monitor = CpuMonitor(interval=0.05)
        monitor.start()
        time.sleep(0.1)
        monitor.stop()

        summary = {"total_requests": 1, "throughput": 10.0}

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_files = export_all_raw_data(
                output_dir=tmp_dir,
                scenario_name="1_client",
                samples=samples,
                cpu_monitor=monitor,
                summary=summary,
            )
            self.assertIn("latency_csv", out_files)
            self.assertIn("latency_json", out_files)
            self.assertIn("cpu_csv", out_files)
            self.assertIn("cpu_json", out_files)
            self.assertIn("summary_json", out_files)
            for path in out_files.values():
                self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
