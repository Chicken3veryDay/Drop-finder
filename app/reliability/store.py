from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.reliability.contracts import AdapterDefinition, AdapterState


class ReliabilityStore:
    """Small durable store for the tracked reliability control-plane boundary.

    The store persists immutable adapter definitions as strict model payloads and
    permits only explicit state transitions. It intentionally owns no network,
    evidence-body, credential, queue, or deployment state.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS adapters (
                    adapter_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    route_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version >= 1),
                    state TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE (source_id, route_id, version)
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS adapters_route_idx "
                "ON adapters (source_id, route_id, version)"
            )

    @staticmethod
    def _payload(adapter: AdapterDefinition) -> str:
        return json.dumps(
            adapter.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> AdapterDefinition:
        return AdapterDefinition.model_validate_json(row["payload_json"])

    def register_adapter(self, adapter: AdapterDefinition) -> AdapterDefinition:
        payload = self._payload(adapter)
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT payload_json FROM adapters WHERE adapter_id = ?",
                (adapter.adapter_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] == payload:
                    return adapter
                raise ValueError(f"adapter id already exists with different content: {adapter.adapter_id}")
            self._connection.execute(
                """
                INSERT INTO adapters (
                    adapter_id, source_id, route_id, version, state,
                    content_sha256, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adapter.adapter_id,
                    adapter.source_id,
                    adapter.route_id,
                    adapter.version,
                    adapter.state.value,
                    adapter.content_sha256,
                    payload,
                    adapter.created_at,
                ),
            )
        return adapter

    def get_adapter(self, adapter_id: str) -> AdapterDefinition | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM adapters WHERE adapter_id = ?",
                (adapter_id,),
            ).fetchone()
        return self._decode(row) if row is not None else None

    def list_adapters(self, source_id: str, route_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload_json FROM adapters
                WHERE source_id = ? AND route_id = ?
                ORDER BY version ASC, adapter_id ASC
                """,
                (source_id, route_id),
            ).fetchall()
        return [self._decode(row).model_dump(mode="json") for row in rows]

    def update_adapter_state(
        self,
        adapter_id: str,
        state: AdapterState,
    ) -> AdapterDefinition:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT payload_json FROM adapters WHERE adapter_id = ?",
                (adapter_id,),
            ).fetchone()
            if row is None:
                raise KeyError(adapter_id)
            current = self._decode(row)
            updated = current.model_copy(update={"state": state})
            payload = self._payload(updated)
            self._connection.execute(
                "UPDATE adapters SET state = ?, payload_json = ? WHERE adapter_id = ?",
                (state.value, payload, adapter_id),
            )
        return updated

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "ReliabilityStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
