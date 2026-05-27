"""
core/memory.py
──────────────
Dual-layer memory
- Short-term : ConversationBufferWindowMemory (in-RAM, last N turns)
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


class MemoryEntry(NamedTuple):
    role: str          # "user" | "assistant"
    content: str
    timestamp: str


class MemoryManager:
    """จัดการ memory ทั้ง short-term และ long-term"""

    def __init__(self, settings: Settings) -> None:
        self._cfg = settings.memory

        # Short-term: เก็บ N turn ล่าสุดใน RAM
        self._short_term: deque[MemoryEntry] = deque(
            maxlen=self._cfg.max_history * 2
        )

        # Long-term: ChromaDB บน disk (persist ข้าม session)
        self._chroma = chromadb.PersistentClient(
            path=str(self._cfg.persist_dir)
        )
        self._collection = self._chroma.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )

        log.info(
            "memory_ready",
            long_term_entries=self._collection.count(),
            short_term_window=self._cfg.max_history,
        )

    # ── Add ───────────────────────────────────────────────────────────────

    def add(self, user_msg: str, assistant_msg: str) -> None:
        """บันทึก turn ใหม่ลงทั้ง short-term และ long-term"""
        ts = datetime.now().isoformat()

        # Short-term
        self._short_term.append(MemoryEntry("user", user_msg, ts))
        self._short_term.append(MemoryEntry("assistant", assistant_msg, ts))

        # Long-term (เก็บเป็น document คู่)
        self._collection.add(
            documents=[f"User: {user_msg}\nAssistant: {assistant_msg}"],
            metadatas=[{"timestamp": ts, "user": user_msg[:100]}],
            ids=[ts],
        )

        log.debug("memory_added", ts=ts)

    # ── Query ─────────────────────────────────────────────────────────────

    def get_history(self) -> list[dict[str, str]]:
        """Short-term history สำหรับใส่ใน LLM context"""
        return [
            {"role": entry.role, "content": entry.content}
            for entry in self._short_term
        ]

    def search_similar(self, query: str, n_results: int = 3) -> list[str]:
        """ค้นหา conversation ที่เกี่ยวข้องใน long-term memory"""
        if self._collection.count() == 0:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, self._collection.count()),
            )
            docs: list[str] = results["documents"][0] if results["documents"] else []
            log.debug("memory_search", query=query[:50], found=len(docs))
            return docs
        except Exception as exc:
            log.error("memory_search_failed", error=str(exc))
            return []

    def clear_short_term(self) -> None:
        """ล้าง short-term memory (เริ่ม conversation ใหม่)"""
        self._short_term.clear()
        log.info("short_term_memory_cleared")

    @property
    def long_term_count(self) -> int:
        return self._collection.count()
