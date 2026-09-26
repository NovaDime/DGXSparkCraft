from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock


class MeetingStore:
    """Durable snapshots; each state/event transition is one SQLite transaction."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        self.connection.commit()

    def save(self, meeting: dict) -> None:
        serialized = json.dumps(meeting, ensure_ascii=False, allow_nan=False)
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO meetings(id,created_at,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (meeting["id"], meeting["created_at"], serialized),
            )

    def get(self, meeting_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute("SELECT payload FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def all(self) -> list[dict]:
        with self._lock:
            rows = self.connection.execute("SELECT payload FROM meetings ORDER BY created_at DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def summaries(self, deleted=False) -> list[dict]:
        fields = ("id", "topic", "status", "provider_mode", "created_at", "updated_at", "current_round", "max_rounds", "include_reviewer")
        return [{key: item[key] for key in fields} for item in self.all() if bool(item.get("deleted")) == deleted]

    def close(self):
        with self._lock:
            self.connection.close()
