from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

DEFAULT_PROFILE_ID = "local_default"
MAX_TERM_SAMPLES = 5


class HistoryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, column_sql: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    mode TEXT NOT NULL,
                    voice_text TEXT NOT NULL,
                    final_text TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS term_stats (
                    term TEXT PRIMARY KEY,
                    source TEXT NOT NULL CHECK(source IN ('auto', 'manual')),
                    count INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS term_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL DEFAULT 'local_default',
                    term TEXT NOT NULL,
                    audio_path TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    quality_score REAL NOT NULL,
                    mfcc_fingerprint BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(term) REFERENCES term_stats(term) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._ensure_column(
                conn,
                "term_stats",
                "profile_id",
                "profile_id TEXT NOT NULL DEFAULT 'local_default'",
            )
            self._ensure_column(
                conn,
                "term_samples",
                "profile_id",
                "profile_id TEXT NOT NULL DEFAULT 'local_default'",
            )

            cleanup_flag = conn.execute(
                "SELECT value FROM app_meta WHERE key = 'auto_terms_purged'"
            ).fetchone()
            if cleanup_flag is None:
                conn.execute("DELETE FROM term_stats WHERE source = 'auto'")
                conn.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('auto_terms_purged', '1')"
                )
            conn.commit()

    def _normalize_term(self, term: str) -> str:
        return term.strip()

    def _status_from_sample_count(self, sample_count: int) -> str:
        return "active" if sample_count > 0 else "pending"

    def _sample_count(self, conn: sqlite3.Connection, term: str, profile_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM term_samples WHERE term = ? AND profile_id = ?",
            (term, profile_id),
        ).fetchone()
        return int(row["n"]) if row else 0

    def _safe_delete_file(self, raw_path: str) -> None:
        try:
            path = Path(raw_path)
            path.unlink(missing_ok=True)
            parent = path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            return

    def _ensure_manual_term(self, conn: sqlite3.Connection, term: str, profile_id: str) -> bool:
        row = conn.execute(
            "SELECT term FROM term_stats WHERE term = ?",
            (term,),
        ).fetchone()
        existed = row is not None
        if existed:
            conn.execute(
                """
                UPDATE term_stats
                SET source = 'manual',
                    count = CASE WHEN count < 1 THEN 1 ELSE count END,
                    profile_id = ?,
                    updated_at = datetime('now')
                WHERE term = ?
                """,
                (profile_id, term),
            )
        else:
            conn.execute(
                """
                INSERT INTO term_stats(term, source, count, profile_id, updated_at)
                VALUES (?, 'manual', 1, ?, datetime('now'))
                """,
                (term, profile_id),
            )
        return existed

    def record_transcript(
        self,
        *,
        mode: str,
        voice_text: str,
        final_text: str,
        duration_seconds: int,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO transcripts(mode, voice_text, final_text, duration_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (mode, voice_text, final_text, max(0, int(duration_seconds))),
            )
            conn.commit()

    def add_manual_term(self, term: str, profile_id: str = DEFAULT_PROFILE_ID) -> dict[str, Any]:
        cleaned = self._normalize_term(term)
        if not cleaned:
            return {
                "ok": True,
                "term": "",
                "existed": False,
                "sample_count": 0,
                "status": "pending",
            }

        with self._lock, self._connect() as conn:
            existed = self._ensure_manual_term(conn, cleaned, profile_id)
            sample_count = self._sample_count(conn, cleaned, profile_id)
            conn.commit()

        return {
            "ok": True,
            "term": cleaned,
            "existed": existed,
            "sample_count": sample_count,
            "status": self._status_from_sample_count(sample_count),
        }

    def add_term_sample(
        self,
        *,
        term: str,
        audio_path: str,
        duration_ms: int,
        quality_score: float,
        mfcc_fingerprint: bytes,
        profile_id: str = DEFAULT_PROFILE_ID,
    ) -> dict[str, Any]:
        cleaned = self._normalize_term(term)
        if not cleaned:
            raise ValueError("term is empty")

        with self._lock, self._connect() as conn:
            self._ensure_manual_term(conn, cleaned, profile_id)

            existing_count = self._sample_count(conn, cleaned, profile_id)
            if existing_count >= MAX_TERM_SAMPLES:
                raise ValueError("sample limit reached (max 5)")

            cursor = conn.execute(
                """
                INSERT INTO term_samples(profile_id, term, audio_path, duration_ms, quality_score, mfcc_fingerprint, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    profile_id,
                    cleaned,
                    audio_path,
                    max(1, int(duration_ms)),
                    float(quality_score),
                    mfcc_fingerprint,
                ),
            )
            conn.execute(
                """
                UPDATE term_stats
                SET source = 'manual',
                    profile_id = ?,
                    count = CASE WHEN count < 1 THEN 1 ELSE count END,
                    updated_at = datetime('now')
                WHERE term = ?
                """,
                (profile_id, cleaned),
            )
            conn.commit()
            sample_id = int(cursor.lastrowid)
            sample_count = existing_count + 1

        return {
            "ok": True,
            "sample_id": sample_id,
            "sample_count": sample_count,
            "status": self._status_from_sample_count(sample_count),
        }

    def export_term_samples_blob(self, term: str, profile_id: str = DEFAULT_PROFILE_ID) -> str:
        cleaned = self._normalize_term(term)
        if not cleaned:
            return ""

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, duration_ms, created_at, audio_path
                FROM term_samples
                WHERE term = ? AND profile_id = ?
                ORDER BY id DESC
                """,
                (cleaned, profile_id),
            ).fetchall()

        lines = [
            f"{int(row['id'])}\t{int(row['duration_ms'])}\t{row['created_at']}\t{row['audio_path']}"
            for row in rows
        ]
        return "\n".join(lines)

    def delete_term_sample(
        self,
        term: str,
        sample_id: int,
        profile_id: str = DEFAULT_PROFILE_ID,
    ) -> dict[str, Any]:
        cleaned = self._normalize_term(term)
        if not cleaned:
            return {"ok": True, "sample_count": 0, "status": "pending"}

        deleted_path = ""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT audio_path
                FROM term_samples
                WHERE id = ? AND term = ? AND profile_id = ?
                """,
                (int(sample_id), cleaned, profile_id),
            ).fetchone()
            if row is not None:
                deleted_path = str(row["audio_path"])
                conn.execute(
                    "DELETE FROM term_samples WHERE id = ? AND term = ? AND profile_id = ?",
                    (int(sample_id), cleaned, profile_id),
                )
                conn.execute(
                    "UPDATE term_stats SET updated_at = datetime('now') WHERE term = ?",
                    (cleaned,),
                )
            sample_count = self._sample_count(conn, cleaned, profile_id)
            conn.commit()

        if deleted_path:
            self._safe_delete_file(deleted_path)

        return {
            "ok": True,
            "sample_count": sample_count,
            "status": self._status_from_sample_count(sample_count),
        }

    def delete_term(self, term: str, profile_id: str = DEFAULT_PROFILE_ID) -> bool:
        cleaned = self._normalize_term(term)
        if not cleaned:
            return False

        sample_paths: list[str] = []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT audio_path FROM term_samples WHERE term = ? AND profile_id = ?",
                (cleaned, profile_id),
            ).fetchall()
            sample_paths = [str(row["audio_path"]) for row in rows]

            conn.execute(
                "DELETE FROM term_samples WHERE term = ? AND profile_id = ?",
                (cleaned, profile_id),
            )
            cursor = conn.execute(
                "DELETE FROM term_stats WHERE term = ? AND profile_id = ?",
                (cleaned, profile_id),
            )
            conn.commit()
            deleted = cursor.rowcount > 0

        for sample_path in sample_paths:
            self._safe_delete_file(sample_path)
        return deleted

    def export_terms_blob(
        self,
        *,
        query: str = "",
        status: str = "all",
        limit: int = 300,
        filter_mode: str | None = None,
        min_auto_count: int | None = None,
    ) -> str:
        del filter_mode, min_auto_count

        normalized_status = status if status in {"all", "active", "pending"} else "all"
        like_query = f"%{query.lower()}%" if query else "%"

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    ts.term AS term,
                    ts.updated_at AS updated_at,
                    COALESCE(COUNT(s.id), 0) AS sample_count
                FROM term_stats ts
                LEFT JOIN term_samples s
                    ON s.term = ts.term
                    AND s.profile_id = ts.profile_id
                WHERE ts.profile_id = ?
                    AND ts.source = 'manual'
                    AND LOWER(ts.term) LIKE ?
                GROUP BY ts.term, ts.updated_at
                ORDER BY
                    sample_count DESC,
                    ts.updated_at DESC,
                    ts.term COLLATE NOCASE ASC
                LIMIT ?
                """,
                (DEFAULT_PROFILE_ID, like_query, max(1, int(limit))),
            ).fetchall()

        lines: list[str] = []
        for row in rows:
            sample_count = int(row["sample_count"])
            current_status = self._status_from_sample_count(sample_count)
            if normalized_status != "all" and normalized_status != current_status:
                continue
            lines.append(f"{row['term']}\t{sample_count}\t{current_status}")
        return "\n".join(lines)

    def get_active_terms(self, profile_id: str = DEFAULT_PROFILE_ID, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    ts.term AS term,
                    COALESCE(COUNT(s.id), 0) AS sample_count,
                    MAX(s.created_at) AS last_sample_at,
                    ts.updated_at AS updated_at
                FROM term_stats ts
                LEFT JOIN term_samples s
                    ON s.term = ts.term
                    AND s.profile_id = ts.profile_id
                WHERE ts.profile_id = ?
                    AND ts.source = 'manual'
                GROUP BY ts.term, ts.updated_at
                HAVING sample_count > 0
                ORDER BY
                    sample_count DESC,
                    COALESCE(MAX(s.created_at), ts.updated_at) DESC,
                    ts.term COLLATE NOCASE ASC
                LIMIT ?
                """,
                (profile_id, max(1, int(limit))),
            ).fetchall()

        return [
            {
                "term": str(row["term"]),
                "sample_count": int(row["sample_count"]),
                "updated_at": str(row["updated_at"]),
                "last_sample_at": str(row["last_sample_at"] or row["updated_at"]),
            }
            for row in rows
        ]

    def load_term_sample_fingerprints(
        self,
        terms: list[str],
        profile_id: str = DEFAULT_PROFILE_ID,
    ) -> dict[str, list[bytes]]:
        cleaned_terms = [self._normalize_term(term) for term in terms if self._normalize_term(term)]
        if not cleaned_terms:
            return {}

        placeholders = ",".join("?" for _ in cleaned_terms)
        params: list[Any] = [profile_id, *cleaned_terms]

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT term, mfcc_fingerprint
                FROM term_samples
                WHERE profile_id = ?
                    AND term IN ({placeholders})
                ORDER BY id DESC
                """,
                params,
            ).fetchall()

        result: dict[str, list[bytes]] = {term: [] for term in cleaned_terms}
        for row in rows:
            term = str(row["term"])
            blob = row["mfcc_fingerprint"]
            if isinstance(blob, memoryview):
                result.setdefault(term, []).append(blob.tobytes())
            else:
                result.setdefault(term, []).append(bytes(blob))
        return result

    def get_summary(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS transcript_count,
                    COALESCE(SUM(duration_seconds), 0) AS total_duration_seconds,
                    COALESCE(SUM(LENGTH(final_text)), 0) AS total_chars
                FROM transcripts
                """
            ).fetchone()

            term_row = conn.execute(
                """
                SELECT COUNT(*) AS active_terms
                FROM (
                    SELECT ts.term
                    FROM term_stats ts
                    LEFT JOIN term_samples s
                        ON s.term = ts.term
                        AND s.profile_id = ts.profile_id
                    WHERE ts.profile_id = ?
                        AND ts.source = 'manual'
                    GROUP BY ts.term
                    HAVING COUNT(s.id) > 0
                )
                """,
                (DEFAULT_PROFILE_ID,),
            ).fetchone()

        transcript_count = int(row["transcript_count"]) if row else 0
        total_duration_seconds = int(row["total_duration_seconds"]) if row else 0
        total_chars = int(row["total_chars"]) if row else 0
        active_terms = int(term_row["active_terms"]) if term_row else 0

        average_chars_per_minute = 0
        if total_duration_seconds > 0:
            average_chars_per_minute = round(total_chars / (total_duration_seconds / 60.0))

        saved_seconds = round(total_duration_seconds * 2.1)

        profile_score = 0
        if total_chars > 0:
            profile_score = min(99, max(1, active_terms * 6))

        return {
            "transcript_count": transcript_count,
            "total_duration_seconds": total_duration_seconds,
            "total_chars": total_chars,
            "average_chars_per_minute": average_chars_per_minute,
            "saved_seconds": saved_seconds,
            "profile_score": profile_score,
        }
