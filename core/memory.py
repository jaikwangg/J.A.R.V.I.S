"""
core/memory.py
──────────────
Dual-layer memory
- Short-term : simple list (in-RAM, last N turns) — ไม่พึ่ง langchain.memory deprecated path
- Long-term  : ChromaDB vector store (persistent, semantic search)
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import NamedTuple

import chromadb

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


class Turn(NamedTuple):
    user: str
    assistant: str
    timestamp: str


class MemoryManager:
    """จัดการ memory ทั้ง short-term และ long-term"""

    def __init__(self, settings: Settings) -> None:
        self._max = settings.memory_max_history

        # Short-term: deque ง่ายๆ ใน RAM ไม่พึ่ง langchain deprecated class
        self._turns: deque[Turn] = deque(maxlen=self._max)

        # Long-term: ChromaDB บน disk
        self._chroma = chromadb.PersistentClient(
            path=str(settings.memory_persist_dir)
        )
        self._collection = self._chroma.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )

        log.info(
            "memory_ready",
            long_term_entries=self._collection.count(),
            short_term_window=self._max,
        )

    # ── Add ───────────────────────────────────────────────────────────────

    def add(self, user_msg: str, assistant_msg: str) -> None:
        ts = datetime.now().isoformat()
        self._turns.append(Turn(user=user_msg, assistant=assistant_msg, timestamp=ts))

        # Long-term
        self._collection.add(
            documents=[f"User: {user_msg}\nAssistant: {assistant_msg}"],
            metadatas=[{"timestamp": ts, "user_preview": user_msg[:100]}],
            ids=[ts],
        )
        log.debug("memory_added", ts=ts)

    # ── Query ─────────────────────────────────────────────────────────────

    def get_history(self) -> list[dict[str, str]]:
        """Short-term history รูปแบบ [{"role": ..., "content": ...}]"""
        result = []
        for turn in self._turns:
            result.append({"role": "user", "content": turn.user})
            result.append({"role": "assistant", "content": turn.assistant})
        return result

    def search_similar(self, query: str, n_results: int = 3) -> list[str]:
        """ค้นหา conversation ที่เกี่ยวข้องใน long-term memory"""
        count = self._collection.count()
        if count == 0:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, count),
            )
            docs: list[str] = results["documents"][0] if results["documents"] else []
            log.debug("memory_search", query=query[:50], found=len(docs))
            return docs
        except Exception as exc:
            log.error("memory_search_failed", error=str(exc))
            return []

    def clear_short_term(self) -> None:
        self._turns.clear()
        log.info("short_term_memory_cleared")

    @property
    def long_term_count(self) -> int:
        return self._collection.count()
