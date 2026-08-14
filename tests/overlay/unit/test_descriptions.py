from codegraph.overlay.descriptions import Description, DescriptionStore, content_hash


def test_write_read_round_trip(tmp_path):
    # Arrange
    store = DescriptionStore(tmp_path)
    desc = Description(
        symbol_id="pkg/mod.py::run",
        body="Run the pipeline.\n\n1. Load config\n2. Execute",
        hash_at_write="abc123",
        links=["codegraph://pkg/mod.py::load"],
    )
    # Act
    store.write(desc)
    loaded = store.read("pkg/mod.py::run")
    # Assert
    assert loaded.body.startswith("Run the pipeline.")
    assert loaded.links == ["codegraph://pkg/mod.py::load"]
    assert loaded.hash_at_write == "abc123"


def test_mark_stale_flags_changed_symbols(tmp_path):
    store = DescriptionStore(tmp_path)
    store.write(Description(symbol_id="a::f", body="x", hash_at_write=content_hash("old")))
    store.write(Description(symbol_id="a::g", body="y", hash_at_write=content_hash("same")))

    stale = store.mark_stale({"a::f": content_hash("new"), "a::g": content_hash("same")})

    assert [d.symbol_id for d in stale] == ["a::f"]


def test_undescribed_lists_missing_symbols(tmp_path):
    store = DescriptionStore(tmp_path)
    store.write(Description(symbol_id="a::f", body="x"))
    assert store.undescribed(["a::f", "a::g"]) == ["a::g"]
