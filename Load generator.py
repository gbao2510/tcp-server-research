"""Load Generator cơ bản (Client / Load Gen Dev - tuần 1).

Tạo N client chạy đồng thời (mỗi client một thread), mỗi client liên tục gửi
payload 1KB và nhận response cho tới khi hết thời gian (hoặc đủ số request).
Cuối cùng in số request thành công / thất bại.

(Đo latency p95, throughput, CPU và vẽ biểu đồ là việc của Metrics / Analytics
 ở các tuần sau; chương trình này chỉ cần chạy đúng và đếm kết quả cơ bản.)

    python "Load generator.py" --clients 10 --duration 5
    python "Load generator.py" --clients 1 --requests 100 --port 9999
"""
from __future__ import annotations

import argparse
import random
import string
import threading
import time
from dataclasses import dataclass

from client import Client
from protocol import DEFAULT_HOST, DEFAULT_PORT, ProtocolError

PAYLOAD_SIZE = 1024  # 1KB theo yêu cầu


@dataclass
class ClientStats:
    client_id: int
    ok: int = 0
    failed: int = 0
    connected: bool = False
    last_error: str = ""


def make_payload(size: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choices(string.ascii_letters + string.digits, k=size))


def client_worker(
    stats: ClientStats,
    host: str,
    port: int,
    start_barrier: threading.Barrier,
    deadline_holder: dict,
    payload_size: int,
    requests_limit: int | None,
    timeout: float,
) -> None:
    payload = make_payload(payload_size, stats.client_id)
    client = Client(host, port, timeout)
    try:
        client.connect()
        stats.connected = True
    except OSError as exc:
        stats.last_error = f"không kết nối được: {exc}"
    try:
        start_barrier.wait()  # tất cả client xuất phát cùng lúc (kể cả client lỗi, tránh treo)
    except threading.BrokenBarrierError:
        client.close()
        return
    if not stats.connected:
        return

    seq = 0
    while True:
        if requests_limit is not None:
            if seq >= requests_limit:
                break
        elif time.monotonic() >= deadline_holder["deadline"]:
            break

        request_id = f"{stats.client_id}-{seq}"
        try:
            resp = client.request({"id": request_id, "type": "echo", "payload": payload})
            if resp.get("status") == "ok" and resp.get("id") == request_id and resp.get("payload") == payload:
                stats.ok += 1
            else:
                stats.failed += 1
                stats.last_error = f"response không hợp lệ: {str(resp)[:80]}"
        except (OSError, ProtocolError) as exc:
            stats.failed += 1
            stats.last_error = f"{type(exc).__name__}: {exc}"
            client.close()
            try:  # thử kết nối lại một lần, thất bại thì dừng client này
                client.connect()
            except OSError:
                break
        seq += 1
    client.close()


def run(
    host: str,
    port: int,
    clients: int,
    duration: float = 5.0,
    payload_size: int = PAYLOAD_SIZE,
    requests_per_client: int | None = None,
    timeout: float = 10.0,
) -> dict:
    """Chạy load test, trả về dict kết quả cơ bản."""
    deadline_holder: dict = {}

    def on_start() -> None:
        deadline_holder["start"] = time.monotonic()
        deadline_holder["deadline"] = deadline_holder["start"] + duration

    barrier = threading.Barrier(clients, action=on_start)
    all_stats = [ClientStats(i) for i in range(clients)]
    threads = [
        threading.Thread(
            target=client_worker,
            args=(s, host, port, barrier, deadline_holder, payload_size, requests_per_client, timeout),
            name=f"client-{s.client_id}",
        )
        for s in all_stats
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = time.monotonic() - deadline_holder.get("start", time.monotonic())
    ok = sum(s.ok for s in all_stats)
    failed = sum(s.failed for s in all_stats)
    return {
        "clients": clients,
        "connected": sum(s.connected for s in all_stats),
        "requests_ok": ok,
        "requests_failed": failed,
        "elapsed_s": round(elapsed, 3),
        "errors": sorted({s.last_error for s in all_stats if s.last_error}),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Load generator cơ bản cho TCP server")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Cổng TCP server (mặc định 9999)")
    p.add_argument("--clients", type=int, default=1, help="số client đồng thời (kịch bản: 1, 10, 50)")
    p.add_argument("--duration", type=float, default=5.0, help="thời gian chạy (giây)")
    p.add_argument("--requests", type=int, default=None, help="số request mỗi client (bỏ qua --duration)")
    p.add_argument("--payload-size", type=int, default=PAYLOAD_SIZE)
    args = p.parse_args()

    if args.clients < 1:
        p.error("--clients phải >= 1")
    print(f"Chạy {args.clients} client -> {args.host}:{args.port}, payload {args.payload_size}B ...")
    r = run(args.host, args.port, args.clients, args.duration, args.payload_size, args.requests)
    print(f"Client kết nối được : {r['connected']}/{r['clients']}")
    print(f"Request thành công  : {r['requests_ok']}")
    print(f"Request thất bại    : {r['requests_failed']}")
    print(f"Thời gian chạy      : {r['elapsed_s']} s")
    for err in r["errors"]:
        print(f"  ! {err}")
    return 0 if r["requests_failed"] == 0 and r["connected"] == r["clients"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
