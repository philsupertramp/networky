import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DB_PATH = os.getenv("DATABASE_PATH", "/data/network.db")
INTERVAL = int(os.getenv("INTERVAL_SECONDS", "60"))
PING_COUNT = int(os.getenv("PING_COUNT", "5"))

TARGETS_V4 = [
    x.strip()
    for x in os.getenv(
        "PING_TARGETS_V4",
        "1.1.1.1,8.8.8.8"
    ).split(",")
    if x.strip()
]

TARGETS_V6 = [
    x.strip()
    for x in os.getenv(
        "PING_TARGETS_V6",
        "2606:4700:4700::1111,2001:4860:4860::8888"
    ).split(",")
    if x.strip()
]

db_lock = threading.Lock()


def get_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                protocol TEXT NOT NULL,
                target TEXT NOT NULL,
                success INTEGER NOT NULL,
                packet_loss REAL,
                min_ms REAL,
                avg_ms REAL,
                max_ms REAL,
                raw_output TEXT
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_measurements_timestamp
            ON measurements(timestamp)
        """)

        db.commit()


def run_ping(target, protocol):
    command = [
        "ping",
        "-n",
        "-c", str(PING_COUNT),
        "-W", "2",
    ]

    if protocol == "ipv4":
        command.append("-4")
    else:
        command.append("-6")

    command.append(target)

    started = time.monotonic()

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=(PING_COUNT * 3) + 5,
            env={
                **os.environ,
                "LC_ALL": "C",
            },
        )

        elapsed = time.monotonic() - started
        output = result.stdout + result.stderr

    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        output = (exc.stdout or "") + (exc.stderr or "")

    loss_match = re.search(
        r"(\d+(?:\.\d+)?)%\s+packet loss",
        output,
    )

    rtt_match = re.search(
        r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/",
        output,
    )

    packet_loss = float(loss_match.group(1)) if loss_match else None

    min_ms = avg_ms = max_ms = None

    if rtt_match:
        min_ms = float(rtt_match.group(1))
        avg_ms = float(rtt_match.group(2))
        max_ms = float(rtt_match.group(3))

    success = (
        result.returncode == 0
        and packet_loss is not None
        and packet_loss < 100.0
    ) if "result" in locals() else False

    timestamp = datetime.now(timezone.utc).isoformat()

    with db_lock:
        with get_db() as db:
            db.execute(
                """
                INSERT INTO measurements (
                    timestamp,
                    protocol,
                    target,
                    success,
                    packet_loss,
                    min_ms,
                    avg_ms,
                    max_ms,
                    raw_output
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    protocol,
                    target,
                    int(success),
                    packet_loss,
                    min_ms,
                    avg_ms,
                    max_ms,
                    output,
                ),
            )
            db.commit()

    print(
        f"{timestamp} {protocol:5} {target:40} "
        f"loss={packet_loss!s:>6} "
        f"avg={avg_ms!s:>8} "
        f"elapsed={elapsed:.2f}s",
        flush=True,
    )


def collect_once():
    for target in TARGETS_V4:
        run_ping(target, "ipv4")

    for target in TARGETS_V6:
        run_ping(target, "ipv6")


def collector_loop():
    while True:
        started = time.monotonic()

        try:
            collect_once()
        except Exception as exc:
            print(f"collector error: {exc}", flush=True)

        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL - elapsed))


class Handler(BaseHTTPRequestHandler):

    def send_json(self, status, data):
        payload = json.dumps(
            data,
            indent=2,
            default=str,
        ).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return

        if parsed.path == "/latest":
            with db_lock:
                with get_db() as db:
                    rows = db.execute("""
                        SELECT *
                        FROM measurements
                        WHERE id IN (
                            SELECT MAX(id)
                            FROM measurements
                            GROUP BY protocol, target
                        )
                        ORDER BY protocol, target
                    """).fetchall()

            self.send_json(200, [dict(row) for row in rows])
            return

        if parsed.path == "/history":
            params = parse_qs(parsed.query)
            limit = min(
                int(params.get("limit", ["1000"])[0]),
                10000,
            )

            with db_lock:
                with get_db() as db:
                    rows = db.execute(
                        """
                        SELECT
                            timestamp,
                            protocol,
                            target,
                            success,
                            packet_loss,
                            min_ms,
                            avg_ms,
                            max_ms
                        FROM measurements
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()

            self.send_json(200, [dict(row) for row in rows])
            return

        self.send_json(
            404,
            {"error": "not found"},
        )

    def log_message(self, fmt, *args):
        print(
            f"{self.address_string()} - {fmt % args}",
            flush=True,
        )


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    init_db()

    thread = threading.Thread(
        target=collector_loop,
        daemon=True,
    )
    thread.start()

    server = ThreadingHTTPServer(
        ("0.0.0.0", 8080),
        Handler,
    )

    print("network monitor listening on :8080", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
