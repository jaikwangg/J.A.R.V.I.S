"""
core/memory.py
──────────────
Dual-layer memory + Smart Context Summarization

FIX-B: _maybe_summarize ใช้ self._llm.summarize() แทน chat()
        เพื่อหลีกเลี่ยง assistant persona ขณะ summarize
FIX-C: เปลี่ยน seen.add() trick เป็น explicit loop ที่อ่านง่ายและ type-safe
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

import chromadb

from config.settings import Settings
from core.logger import get_logger

if TYPE_CHECKING:
    from services.llm import LLMService

log = get_logger(__name__)

SUMMARIZE_THRESHOLD = 10   # trigger เมื่อ turns เกินนี้
KEEP_RECENT         = 5    # เก็บ turns ล่าสุดไว้กี่ turn หลัง summarize

_SUMMARIZE_PROMPT = """\
สรุปบทสนทนาต่อไปนี้ให้กระชับ ไม่เกิน 3-5 ประโยค
เก็บข้อมูลสำคัญที่อาจจำเป็นในอนาคต เช่น ชื่อ วันที่ การตัดสินใจ สิ่งที่พูดถึง
ห้ามแต่งเนื้อหาเพิ่มเติม

บทสนทนา:
{conversation}

สรุป:"""


class Turn(NamedTuple):
    user: str
    assistant: str
    timestamp: str


class MemoryManager:
    def __init__(self, settings: Settings, llm: "LLMService | None" = None) -> None:
        self._max     = settings.memory_max_history
        self._llm     = llm
        self._turns: deque[Turn] = deque(maxlen=self._max)
        self._summary: str = ""

        self._chroma     = chromadb.PersistentClient(path=str(settings.memory_persist_dir))
        self._collection = self._chroma.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )
        self._summary_col = self._chroma.get_or_create_collection(
            name="summaries",
            metadata={"hnsw:space": "cosine"},
        )
        log.info(
            "memory_ready",
            long_term_entries=self._collection.count(),
            summaries=self._summary_col.count(),
            short_term_window=self._max,
        )

    def set_llm(self, llm: "LLMService") -> None:
        """Inject LLM หลัง init เพื่อหลีกเลี่ยง circular import"""
        self._llm = llm
        log.debug("memory_llm_attached")

    # ── Add ───────────────────────────────────────────────────────────────

    def add(self, user_msg: str, assistant_msg: str) -> None:
        ts = datetime.now().isoformat()
        self._turns.append(Turn(user=user_msg, assistant=assistant_msg, timestamp=ts))

        self._collection.add(
            documents=[f"User: {user_msg}\nAssistant: {assistant_msg}"],
            metadatas=[{"timestamp": ts, "user_preview": user_msg[:100]}],
            ids=[ts],
        )
        log.debug("memory_added", ts=ts)

        if len(self._turns) >= SUMMARIZE_THRESHOLD and self._llm is not None:
            self._maybe_summarize()

    # ── Summarization ─────────────────────────────────────────────────────

    def _maybe_summarize(self) -> None:
        turns_list   = list(self._turns)
        to_summarize = turns_list[:-KEEP_RECENT]
        to_keep      = turns_list[-KEEP_RECENT:]

        if len(to_summarize) < 3:
            return

        conv_text = "\n".join(
            f"User: {t.user}\nAssistant: {t.assistant}" for t in to_summarize
        )
        prompt = _SUMMARIZE_PROMPT.format(conversation=conv_text)

        try:
            log.info("memory_summarizing", turns=len(to_summarize))

            # FIX-B: ใช้ summarize() แทน chat() เพื่อหลีกเลี่ยง assistant persona
            new_summary = self._llm.summarize(prompt)  # type: ignore[union-attr]

            if not new_summary:
                log.warning("memory_summarize_empty_result")
                return

            new_summary  = new_summary.strip()
            combined     = (
                f"{self._summary}\n\n[อัปเดต] {new_summary}"
                if self._summary else new_summary
            )
            self._summary = combined

            ts = datetime.now().isoformat()
            self._summary_col.add(
                documents=[combined],
                metadatas=[{"timestamp": ts, "turns_compressed": len(to_summarize)}],
                ids=[f"summary_{ts}"],
            )

            self._turns = deque(to_keep, maxlen=self._max)

            log.info(
                "memory_summarized",
                compressed=len(to_summarize),
                kept=len(to_keep),
                summary_chars=len(self._summary),
            )
        except Exception as exc:
            log.error("memory_summarize_failed", error=str(exc))

    def force_summarize(self) -> str:
        if not self._turns or self._llm is None:
            return self._summary or "ไม่มีบทสนทนา"
        self._maybe_summarize()
        return self._summary

    # ── Query ─────────────────────────────────────────────────────────────

    def get_history(self) -> list[dict[str, str]]:
        """Short-term history สำหรับ LLM — prepend rolling summary ถ้ามี"""
        result: list[dict[str, str]] = []
        if self._summary:
            result.append({
                "role": "system",
                "content": f"[สรุปบทสนทนาก่อนหน้า]\n{self._summary}",
            })
        for turn in self._turns:
            result.append({"role": "user",      "content": turn.user})
            result.append({"role": "assistant",  "content": turn.assistant})
        return result

    def search_similar(self, query: str, n_results: int = 3) -> list[str]:
        """ค้นหาใน long-term conversations + summaries"""
        found: list[str] = []
        for col in [self._collection, self._summary_col]:
            count = col.count()
            if count == 0:
                continue
            try:
                res = col.query(
                    query_texts=[query],
                    n_results=min(n_results, count),
                )
                found.extend(res["documents"][0] if res["documents"] else [])
            except Exception as exc:
                log.error("memory_search_failed", collection=col.name, error=str(exc))

        # FIX-C: explicit dedup loop แทน seen.add() trick
        seen: set[str] = set()
        unique: list[str] = []
        for doc in found:
            if doc not in seen:
                seen.add(doc)
                unique.append(doc)

        log.debug("memory_search", query=query[:50], found=len(unique))
        return unique[:n_results]

    def clear_short_term(self) -> None:
        self._turns.clear()
        self._summary = ""
        log.info("short_term_memory_cleared")

    @property
    def summary(self) -> str:
        return self._summary

    @property
    def long_term_count(self) -> int:
        return self._collection.count()

    @property
    def short_term_count(self) -> int:
        return len(self._turns)
