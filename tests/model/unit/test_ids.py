from codegraph.model.ids import from_uri, library_id, slugify, symbol_id, to_uri


def test_symbol_id_is_repo_relative():
    # Arrange / Act
    sid = symbol_id("/repo/pkg/mod.py", "load_config", repo_root="/repo")
    # Assert
    assert sid == "pkg/mod.py::load_config"


def test_symbol_id_keeps_absolute_path_outside_root():
    sid = symbol_id("/elsewhere/mod.py", "fn", repo_root="/repo")
    assert sid == "/elsewhere/mod.py::fn"


def test_uri_round_trip():
    sid = symbol_id("pkg/mod.py", "fn")
    assert from_uri(to_uri(sid)) == sid


def test_slugify_is_filesystem_safe():
    assert "/" not in slugify("pkg/mod.py::Class.method")
    assert ":" not in slugify("pkg/mod.py::Class.method")


def test_library_id_prefix():
    assert library_id("requests") == "lib::requests"
