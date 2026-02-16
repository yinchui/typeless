from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from threading import Lock


_COMMON_ZH_STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "一个",
    "一些",
    "然后",
    "就是",
    "如果",
    "因为",
    "所以",
    "今天",
    "现在",
    "时候",
    "内容",
    "事情",
    "问题",
    "可以",
    "需要",
    "希望",
    "还有",
    "这样",
    "那个",
    "这里",
    "那里",
    "一下",
    "进行",
    "已经",
    "没有",
    "不是",
    "非常",
    "可能",
}

_COMMON_EN_STOPWORDS = {
    "the",
    "and",
    "with",
    "that",
    "this",
    "from",
    "have",
    "will",
    "into",
    "about",
    "also",
    "just",
    "your",
    "you",
    "for",
    "are",
    "was",
    "were",
    "been",
    "being",
    "need",
    "make",
    "made",
    "very",
    "more",
    "most",
    "then",
    "than",
}


def _remove_emoji(text: str) -> str:
    emoji_re = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "]",
        flags=re.UNICODE,
    )
    return emoji_re.sub("", text)


def extract_auto_terms(text: str) -> set[str]:
    clean = _remove_emoji(text)
    terms: set[str] = set()

    for token in re.findall(r"[\u4E00-\u9FFF]{2,8}", clean):
        if token in _COMMON_ZH_STOPWORDS:
            continue
        # Avoid storing full long sentence chunks.
        if len(token) > 6:
            continue
        terms.add(token)

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_+\-/.]{2,28}", clean):
        lowered = token.lower()
        if lowered in _COMMON_EN_STOPWORDS:
            continue
        if len(token) < 4:
            continue
        terms.add(token)

    return terms


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
                """
            )

    def _upsert_term(self, conn: sqlite3.Connection, term: str, source: str, increment: int = 1) -> None:
        row = conn.execute(
            "SELECT source, count FROM term_stats WHERE term = ?",
            (term,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO term_stats(term, source, count, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (term, source, max(1, increment)),
            )
            return

        existing_source = row["source"]
        next_source = "manual" if (existing_source == "manual" or source == "manual") else "auto"
        conn.execute(
            """
            UPDATE term_stats
            SET source = ?, count = count + ?, updated_at = datetime('now')
            WHERE term = ?
            """,
            (next_source, max(1, increment), term),
        )

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
            for term in extract_auto_terms(final_text):
                self._upsert_term(conn, term=term, source="auto", increment=1)
            conn.commit()

    def add_manual_term(self, term: str) -> None:
        cleaned = term.strip()
        if not cleaned:
            return
        with self._lock, self._connect() as conn:
            self._upsert_term(conn, term=cleaned, source="manual", increment=1)
            conn.commit()

    def delete_term(self, term: str) -> bool:
        cleaned = term.strip()
        if not cleaned:
            return False
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM term_stats WHERE term = ?",
                (cleaned,),
            )
            conn.commit()
            return cursor.rowcount > 0

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
                SELECT COUNT(*) AS frequent_terms
                FROM term_stats
                WHERE source = 'manual' OR count >= 2
                """
            ).fetchone()

        transcript_count = int(row["transcript_count"]) if row else 0
        total_duration_seconds = int(row["total_duration_seconds"]) if row else 0
        total_chars = int(row["total_chars"]) if row else 0
        frequent_terms = int(term_row["frequent_terms"]) if term_row else 0

        average_chars_per_minute = 0
        if total_duration_seconds > 0:
            average_chars_per_minute = round(total_chars / (total_duration_seconds / 60.0))

        saved_seconds = round(total_duration_seconds * 2.1)

        profile_score = 0
        if total_chars > 0:
            profile_score = min(99, max(1, frequent_terms * 6))

        return {
            "transcript_count": transcript_count,
            "total_duration_seconds": total_duration_seconds,
            "total_chars": total_chars,
            "average_chars_per_minute": average_chars_per_minute,
            "saved_seconds": saved_seconds,
            "profile_score": profile_score,
        }

    def export_terms_blob(self, *, query: str = "", filter_mode: str = "all", min_auto_count: int = 3, limit: int = 300) -> str:
        like_query = f"%{query.lower()}%" if query else "%"
        normalized_filter = filter_mode if filter_mode in {"all", "auto", "manual"} else "all"

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT term, source, count
                FROM term_stats
                WHERE
                    (
                        source = 'manual'
                        OR count >= ?
                    )
                    AND (? = 'all' OR source = ?)
                    AND LOWER(term) LIKE ?
                ORDER BY
                    CASE WHEN source = 'manual' THEN 0 ELSE 1 END,
                    count DESC,
                    term COLLATE NOCASE ASC
                LIMIT ?
                """,
                (max(1, min_auto_count), normalized_filter, normalized_filter, like_query, max(1, limit)),
            ).fetchall()

        lines = [f"{row['term']}\t{row['source']}\t{row['count']}" for row in rows]
        return "\n".join(lines)

