"""Load Generator (Client / Load Gen Dev) - tuần 2: đo Latency + đếm request.

N client chạy đồng thời (mỗi client một thread, một kết nối bền). Mỗi client liên
tục gửi payload 1KB, chờ response, đo thời gian của từng request bằng
time.perf_counter() và phân loại lỗi (timeout, connection_closed, ...).

    python load_generator.py --clients 10 --duration 5
    python load_generator.py --clients 50 --duration 10 --csv results/raw_50.csv
    python load_generator.py --clients 3 --requests 100 --timeout 2
"""
from __future__ import annotations

import argparse
import random
import socket
import string
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from client import Client
from src.metrics import Sample, format_summary, summarize, write_csv
from src.protocol import ProtocolError

PAYLOAD_SIZE = 1024  # 1KB theo yêu cầu


def make_payload(size: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choices(string.ascii_letters + string.digits, k=size))


def classify_error(exc: BaseException) -> str:
    """Gom lỗi thành nhóm để thống kê."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, ConnectionResetError):
        return "connection_closed"
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError)):
        return "connection_reset"
    if isinstance(exc, ProtocolError):
        return "protocol_error"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused"
    return "os_error"


@dataclass
class LoadResult:
    clients: int
    connected: int
    elapsed_s: float
    samples: list[Sample]
    summary: dict
    connect_errors: list[str] = field(default_factory=list)


@dataclass
class _Shared:
    start: float = 0.0
    deadline: float = 0.0


@dataclass
class _WorkerOut:
    connected: bool = False
    samples: list[Sample] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _worker(cid, host, port, timeout, payload_size, requests_limit, barrier, shared, out) -> None:
    result = _WorkerOut()
    out[cid] = result
    payload = make_payload(payload_size, cid)
    client = Client(host, port, timeout)
    try:
        client.connect()
        result.connected = True
    except OSError as exc:
        result.errors.append(f"{classify_error(exc)}: {exc}")
    try:
        barrier.wait()  # mọi client xuất phát cùng lúc, kể cả client kết nối lỗi
    except threading.BrokenBarrierError:
        client.close()
        return
    if not result.connected:
        return

    seq = 0
    while True:
        if requests_limit is not None:
            if seq >= requests_limit:
                break
        elif time.perf_counter() >= shared.deadline:
            break

        request_id = f"{cid}-{seq}"
        ok, err, reconnect = True, "", False
        start = time.perf_counter()
        try:
            resp = client.request({"id": request_id, "type": "echo", "payload": payload})
            if resp.get("status") != "ok":
                ok, err = False, f"bad_response:{resp.get('code', 'unknown')}"
            elif resp.get("id") != request_id or resp.get("payload") != payload:
                ok, err, reconnect = False, "bad_response:mismatch", True  # luồng có thể lệch -> kết nối lại
        except (OSError, ProtocolError) as exc:
            ok, err, reconnect = False, classify_error(exc), True
        latency_ms = (time.perf_counter() - start) * 1000.0
        result.samples.append(Sample(cid, seq, start - shared.start, latency_ms, ok, err))
        seq += 1

        if reconnect:  # kết nối cũ không còn tin cậy: đóng và thử kết nối lại một lần
            client.close()
            try:
                client.connect()
            except OSError as exc:
                result.errors.append(f"reconnect {classify_error(exc)}: {exc}")
                break
    client.close()


def run(
    host: str,
    port: int,
    clients: int,
    duration: float = 5.0,
    payload_size: int = PAYLOAD_SIZE,
    requests_per_client: int | None = None,
    timeout: float = 5.0,
    warmup: float = 0.0,
) -> LoadResult:
    """Chạy load test.

    - Mặc định chạy theo thời gian `duration` giây.
    - Nếu `requests_per_client` được đặt: mỗi client gửi đúng số request đó.
    """
    if clients < 1:
        raise ValueError("clients phải >= 1")
    shared = _Shared()

    def on_start() -> None:
        shared.start = time.perf_counter()
        shared.deadline = shared.start + duration

    barrier = threading.Barrier(clients, action=on_start)
    out: dict[int, _WorkerOut] = {}
    threads = [
        threading.Thread(
            target=_worker,
            args=(i, host, port, timeout, payload_size, requests_per_client, barrier, shared, out),
            name=f"client-{i}",
        )
        for i in range(clients)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = time.perf_counter() - shared.start if shared.start else 0.0
    samples = sorted((s for w in out.values() for s in w.samples), key=lambda s: s.t_start)
    errors = [e for w in out.values() for e in w.errors]
    return LoadResult(
        clients=clients,
        connected=sum(w.connected for w in out.values()),
        elapsed_s=round(elapsed, 3),
        samples=samples,
        summary=summarize(samples, elapsed, warmup),
        connect_errors=errors,
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Load generator cho TCP server (Length-Prefix + JSON)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--clients", type=int, default=1, help="số client đồng thời (kịch bản: 1, 10, 50)")
    p.add_argument("--duration", type=float, default=5.0, help="thời gian chạy (giây)")
    p.add_argument("--requests", type=int, default=None, help="số request mỗi client (bỏ qua --duration)")
    p.add_argument("--payload-size", type=int, default=PAYLOAD_SIZE)
    p.add_argument("--timeout", type=float, default=5.0, help="timeout mỗi request (giây)")
    p.add_argument("--warmup", type=float, default=0.0, help="loại N giây đầu khỏi thống kê")
    p.add_argument("--csv", type=Path, default=None, help="ghi dữ liệu thô từng request ra CSV")
    args = p.parse_args()
    if args.clients < 1:
        p.error("--clients phải >= 1")

    print(f"Chạy {args.clients} client -> {args.host}:{args.port}, payload {args.payload_size}B ...")
    r = run(args.host, args.port, args.clients, args.duration, args.payload_size,
            args.requests, args.timeout, args.warmup)
    print(format_summary(r.summary, r.clients, r.connected))
    for e in sorted(set(r.connect_errors)):
        print(f"  ! {e}")
    if args.csv:
        write_csv(r.samples, args.csv)
        print(f"Đã ghi {len(r.samples)} mẫu -> {args.csv}")
    return 0 if r.summary["requests_failed"] == 0 and r.connected == r.clients else 1


if __name__ == "__main__":
    raise SystemExit(main())