import pytest

from codegraph.overlay.reasons import Reason, ReasonLog


def test_record_and_read_by_symbol(tmp_path):
    # Arrange
    log = ReasonLog(tmp_path)
    # Act
    log.record(Reason(symbol_id="a::f", why="handles legacy input shape", kind="exists"))
    log.record(Reason(symbol_id="a::f", why="tightened validation", kind="changed", trace_id="t1"))
    # Assert
    entries = log.for_symbol("a::f")
    assert len(entries) == 2
    assert entries[1].trace_id == "t1"


def test_read_by_trace_id(tmp_path):
    log = ReasonLog(tmp_path)
    log.record(Reason(symbol_id="a::f", why="w", trace_id="t9"))
    assert [r.symbol_id for r in log.for_trace("t9")] == ["a::f"]


def test_invalid_kind_fails_loud(tmp_path):
    log = ReasonLog(tmp_path)
    with pytest.raises(ValueError):
        log.record(Reason(symbol_id="a::f", why="w", kind="vibes"))
