"""Tests for MemoryManager with summarization"""
import pytest
from unittest.mock import MagicMock
from config.settings import Settings
from core.memory import MemoryManager, SUMMARIZE_THRESHOLD, KEEP_RECENT


@pytest.fixture
def mem_with_llm(tmp_path):
    s = Settings(
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        memory_persist_dir=tmp_path / "memory",
        memory_max_history=20,
    )
    mock_llm = MagicMock()
    # FIX: mock summarize() ไม่ใช่ chat()
    mock_llm.summarize.return_value = "สรุป: คุยเรื่องทั่วไปและนัดหมาย"
    mem = MemoryManager(s, llm=mock_llm)
    return mem, mock_llm


def test_summarize_calls_summarize_not_chat(mem_with_llm):
    """ต้องเรียก summarize() ไม่ใช่ chat() — FIX-B"""
    mem, mock_llm = mem_with_llm
    for i in range(SUMMARIZE_THRESHOLD + 1):
        mem.add(f"user {i}", f"reply {i}")
    assert mock_llm.summarize.called, "summarize() ต้องถูกเรียก"
    assert not mock_llm.chat.called, "chat() ต้องไม่ถูกเรียกตอน summarize"


def test_summary_in_history(mem_with_llm):
    mem, _ = mem_with_llm
    for i in range(SUMMARIZE_THRESHOLD + 1):
        mem.add(f"user {i}", f"reply {i}")
    history = mem.get_history()
    if mem.summary:
        assert history[0]["role"] == "system"
        assert "สรุป" in history[0]["content"]


def test_short_term_trimmed_after_summarize(mem_with_llm):
    mem, _ = mem_with_llm
    for i in range(SUMMARIZE_THRESHOLD):
        mem.add(f"user {i}", f"reply {i}")
    assert mem.short_term_count <= KEEP_RECENT


def test_dedup_search_results(mem_with_llm):
    """FIX-C: ผลลัพธ์จาก search_similar ต้องไม่มีซ้ำ"""
    mem, _ = mem_with_llm
    mem.add("สวัสดี", "สวัสดีครับ")
    results = mem.search_similar("สวัสดี", n_results=5)
    assert len(results) == len(set(results)), "ผลลัพธ์ต้องไม่มีซ้ำ"


def test_set_llm_after_init(tmp_path):
    s = Settings(
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        memory_persist_dir=tmp_path / "memory",
    )
    mem = MemoryManager(s)
    assert mem._llm is None
    mock_llm = MagicMock()
    mem.set_llm(mock_llm)
    assert mem._llm is mock_llm


def test_empty_summarize_result_does_not_crash(mem_with_llm):
    """ถ้า LLM คืน empty string ต้อง skip gracefully"""
    mem, mock_llm = mem_with_llm
    mock_llm.summarize.return_value = ""
    for i in range(SUMMARIZE_THRESHOLD + 1):
        mem.add(f"user {i}", f"reply {i}")
    # ไม่ควร crash และ summary ยังว่างอยู่
    assert mem.summary == ""
