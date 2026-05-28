"""Tests for MemoryManager"""
import pytest
from config.settings import Settings
from core.memory import MemoryManager


@pytest.fixture
def mem(tmp_path):
    s = Settings(
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        memory_persist_dir=tmp_path / "memory",
    )
    return MemoryManager(s)


def test_add_and_get_history(mem):
    mem.add("สวัสดี", "สวัสดีครับ")
    history = mem.get_history()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_max_history_window(mem):
    # fill beyond window
    for i in range(25):
        mem.add(f"user {i}", f"reply {i}")
    history = mem.get_history()
    # max_history=20 → 40 messages max
    assert len(history) <= mem._max * 2


def test_clear_short_term(mem):
    mem.add("test", "reply")
    mem.clear_short_term()
    assert mem.get_history() == []


def test_long_term_count(mem):
    assert mem.long_term_count == 0
    mem.add("hello", "hi")
    assert mem.long_term_count == 1
