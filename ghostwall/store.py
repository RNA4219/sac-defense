"""Synthetic records and minimal, session-scoped evidence in SQLite."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .core import DATASET_VERSION, digest

STAGES = (
    "DISCOVERY",
    "BAIT_ACCEPTED",
    "DATA_DISCOVERY",
    "CONFIDENCE_BUILDING",
    "FALSE_SUCCESS",
    "SATIATED",
)
GIVEN = ("Airi", "Haru", "Mio", "Ren", "Sora", "Yuna", "Kai", "Nagi")
FAMILY = ("Akamine", "Hoshina", "Kisaragi", "Mizuno", "Naruse", "Shiomi", "Takase", "Yukishiro")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path, key: bytes) -> None:
        self.path = path
        self.key = key
        self.seed_id = hashlib.sha256(key).hexdigest()[:16]

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS customers (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                  phone TEXT NOT NULL, address TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                  amount_cents INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS support (
                  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                  order_id TEXT NOT NULL REFERENCES orders(id),
                  topic TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                  sid TEXT PRIMARY KEY, stage TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exports (
                  job_id TEXT PRIMARY KEY, sid TEXT NOT NULL,
                  created_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
                  sha256 TEXT NOT NULL, record_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                  sid TEXT NOT NULL, kind TEXT NOT NULL, route TEXT NOT NULL,
                  stage TEXT NOT NULL, path TEXT NOT NULL, synthetic_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS host_signals (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                  sid TEXT NOT NULL, kind TEXT NOT NULL, severity INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_sid ON events(sid);
                CREATE INDEX IF NOT EXISTS idx_signals_sid ON host_signals(sid);
                """
            )
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT value FROM meta WHERE key='seed_id'").fetchone()
            if existing and existing[0] != self.seed_id:
                raise ValueError("database was created with another deployment key")
            version = db.execute("SELECT value FROM meta WHERE key='dataset_version'").fetchone()
            if version and version[0] != DATASET_VERSION:
                raise ValueError("unknown dataset version")
            if not existing:
                db.execute("INSERT INTO meta VALUES ('seed_id', ?)", (self.seed_id,))
                db.execute("INSERT INTO meta VALUES ('dataset_version', ?)", (DATASET_VERSION,))
                db.execute("INSERT INTO meta VALUES ('created_at', '2025-01-01T00:00:00Z')")
                self._populate(db)
            errors = db.execute("PRAGMA foreign_key_check").fetchall()
            if errors:
                raise ValueError("synthetic database has broken foreign keys")

    def _choice(self, label: str, length: int) -> int:
        return int.from_bytes(digest(self.key, f"{DATASET_VERSION}:{label}")[:8], "big") % length

    def _populate(self, db: sqlite3.Connection) -> None:
        for number in range(1, 49):
            cid = f"C{number:06d}"
            given = GIVEN[self._choice(f"given:{cid}", len(GIVEN))]
            family = FAMILY[self._choice(f"family:{cid}", len(FAMILY))]
            city = ("Sample City", "Example Bay", "Fiction Harbor")[self._choice(f"city:{cid}", 3)]
            db.execute(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)",
                (
                    cid,
                    f"{given} {family}",
                    f"{given.lower()}.{family.lower()}.{number}@example.invalid",
                    f"202-555-{100 + number:04d}",
                    f"{number * 7} Example Avenue, {city}",
                    f"2025-01-{1 + number % 28:02d}T09:00:00Z",
                ),
            )
            for order_no in (1, 2):
                oid = f"O{number:06d}-{order_no}"
                cents = 1200 + self._choice(f"amount:{oid}", 30000)
                db.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                    (oid, cid, cents, "fulfilled", f"2025-02-{1 + number % 28:02d}T10:00:00Z"),
                )
            db.execute(
                "INSERT INTO support VALUES (?, ?, ?, ?, ?)",
                (
                    f"T{number:06d}",
                    cid,
                    f"O{number:06d}-1",
                    "delivery confirmation",
                    f"2025-03-{1 + number % 28:02d}T11:00:00Z",
                ),
            )

    def metadata(self) -> dict[str, str]:
        with self.connect() as db:
            return {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM meta")}

    def rows(self, table: str, customer_id: str | None = None) -> list[dict[str, Any]]:
        if table not in {"customers", "orders", "support"}:
            raise ValueError("invalid table")
        with self.connect() as db:
            if customer_id and table != "customers":
                result = db.execute(f"SELECT * FROM {table} WHERE customer_id=? ORDER BY id", (customer_id,))
            else:
                result = db.execute(f"SELECT * FROM {table} ORDER BY id")
            return [dict(row) for row in result]

    def customer(self, cid: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
            return dict(row) if row else None

    def stage(self, sid: str, target: str | None = None) -> str:
        with self.connect() as db:
            if target is not None:
                db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT stage FROM sessions WHERE sid=?", (sid,)).fetchone()
            current = row[0] if row else STAGES[0]
            if target is not None:
                if target not in STAGES:
                    raise ValueError("invalid stage")
                if STAGES.index(target) > STAGES.index(current):
                    current = target
                db.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(sid) DO UPDATE SET stage=excluded.stage,updated_at=excluded.updated_at",
                    (sid, current, utc_now()),
                )
            return current

    def event(self, sid: str, kind: str, route: str, stage: str, path: str, count: int = 0) -> None:
        # Never store request bodies, query strings, credentials, IPs, or headers.
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(at,sid,kind,route,stage,path,synthetic_count) VALUES (?,?,?,?,?,?,?)",
                (utc_now(), sid, kind, route, stage, path[:120], count),
            )

    def host_signal(self, sid: str, kind: str, severity: int) -> None:
        if not 0 <= severity <= 10 or kind not in {"decoy_file_access", "suspicious_process", "network_probe"}:
            raise ValueError("invalid host signal")
        with self.connect() as db:
            db.execute("INSERT INTO host_signals(at,sid,kind,severity) VALUES (?,?,?,?)", (utc_now(), sid, kind, severity))

    def risk(self, sid: str) -> int:
        with self.connect() as db:
            row = db.execute("SELECT MAX(severity) FROM host_signals WHERE sid=?", (sid,)).fetchone()
            return int(row[0] or 0)

    def export_csv(self) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=("id", "name", "email", "phone", "address", "created_at"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows("customers"))
        return output.getvalue().encode("utf-8")

    def export(self, sid: str) -> dict[str, Any]:
        job_id = hmac.new(self.key, f"export:{sid}".encode(), hashlib.sha256).hexdigest()[:24]
        data = self.export_csv()
        sha = hashlib.sha256(data).hexdigest()
        count = len(self.rows("customers"))
        created_at = self.metadata()["created_at"]
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO exports VALUES (?,?,?,?,?,?)",
                (job_id, sid, created_at, utc_now(), sha, count),
            )
        return {"job_id": job_id, "status": "completed", "record_count": count}

    def manifest(self, sid: str, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM exports WHERE job_id=? AND sid=?", (job_id, sid)).fetchone()
        if not row:
            return None
        return {
            "job_id": job_id,
            "status": "completed",
            "record_count": row["record_count"],
            "sha256": row["sha256"],
            "created_at": row["created_at"],
            "dataset_version": DATASET_VERSION,
        }

    def summary(self) -> dict[str, Any]:
        with self.connect() as db:
            routes = {row[0]: row[1] for row in db.execute("SELECT route,COUNT(*) FROM events GROUP BY route")}
            stages = {row[0]: row[1] for row in db.execute("SELECT stage,COUNT(*) FROM sessions GROUP BY stage")}
            count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"events": count, "routes": routes, "stages": stages, "dataset_version": DATASET_VERSION}

    def prune(self, cutoff: str) -> dict[str, int]:
        removed: dict[str, int] = {}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for table, column in (
                ("events", "at"),
                ("host_signals", "at"),
                ("exports", "recorded_at"),
                ("sessions", "updated_at"),
            ):
                cursor = db.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
                removed[table] = cursor.rowcount
        return removed

    def collision_check(self, registry: Path) -> dict[str, int]:
        """Compare an operator-supplied registry in memory; never persist its rows."""
        customers = self.rows("customers")
        emails = {str(row["email"]).casefold() for row in customers}
        phones = {str(row["phone"]) for row in customers}
        names_and_addresses = {(str(row["name"]).casefold(), str(row["address"]).casefold()) for row in customers}
        checked = collisions = uncheckable = 0
        with registry.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or ())
            if not ("email" in fields or "phone" in fields or {"name", "address"} <= fields):
                raise ValueError("registry needs email, phone, or both name and address")
            for row in reader:
                checked += 1
                email = (row.get("email") or "").strip().casefold()
                phone = (row.get("phone") or "").strip()
                name = (row.get("name") or "").strip().casefold()
                address = (row.get("address") or "").strip().casefold()
                if not (email or phone or (name and address)):
                    uncheckable += 1
                if (email and email in emails) or (phone and phone in phones) or (name and address and (name, address) in names_and_addresses):
                    collisions += 1
        return {"records_checked": checked, "collisions": collisions, "uncheckable": uncheckable}
