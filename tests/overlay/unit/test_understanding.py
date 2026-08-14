import pytest

from codegraph.overlay.understanding import UnderstandingEntry, UnderstandingLedger


def test_latest_entry_wins(tmp_path):
    # Arrange
    ledger = UnderstandingLedger(tmp_path)
    ledger.record(UnderstandingEntry(symbol_id="a::f", state="walked", hash_at_review="h1"))
    ledger.record(UnderstandingEntry(symbol_id="a::f", state="owned", hash_at_review="h1"))
    # Act
    states = ledger.effective({"a::f": "h1"})
    # Assert
    assert states == {"a::f": "owned"}


def test_hash_drift_voids_to_unreviewed(tmp_path):
    ledger = UnderstandingLedger(tmp_path)
    ledger.record(UnderstandingEntry(symbol_id="a::f", state="owned", hash_at_review="old"))
    assert ledger.effective({"a::f": "new"}) == {}


def test_missing_hash_never_grants_understanding(tmp_path):
    ledger = UnderstandingLedger(tmp_path)
    ledger.record(UnderstandingEntry(symbol_id="a::f", state="walked", hash_at_review=None))
    assert ledger.effective({"a::f": "h"}) == {}


def test_invalid_state_fails_loud(tmp_path):
    with pytest.raises(ValueError):
        UnderstandingLedger(tmp_path).record(
            UnderstandingEntry(symbol_id="a::f", state="vibes")
        )


def test_revoked_then_rereviewed(tmp_path):
    # symbol changed (void), then reviewed again at the new hash
    ledger = UnderstandingLedger(tmp_path)
    ledger.record(UnderstandingEntry(symbol_id="a::f", state="owned", hash_at_review="v1"))
    ledger.record(UnderstandingEntry(symbol_id="a::f", state="walked", hash_at_review="v2"))
    assert ledger.effective({"a::f": "v2"}) == {"a::f": "walked"}
