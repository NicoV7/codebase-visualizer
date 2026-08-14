from codegraph.model.graph import Edge, Graph, Node, synthesize_library_nodes


def _graph():
    return Graph(
        nodes=[
            Node(id="a.py::<file>", kind="file", name="a.py", path="/repo/a.py"),
            Node(id="module::sample_pkg", kind="module", name="sample_pkg", is_external=True),
            Node(id="module::local.helper", kind="module", name="local.helper", path="/repo/helper.py"),
        ],
        edges=[
            Edge(src="a.py::<file>", dst="module::sample_pkg", kind="imports"),
            Edge(src="a.py::<file>", dst="module::local.helper", kind="imports"),
        ],
    )


def test_external_imports_become_library_nodes():
    # Act
    result = synthesize_library_nodes(_graph(), "/repo")
    # Assert
    libs = [n for n in result.nodes if n.kind == "library"]
    assert [n.name for n in libs] == ["sample_pkg"]
    kinds = {e.kind for e in result.edges}
    assert "uses_library" in kinds


def test_internal_imports_stay_import_edges():
    result = synthesize_library_nodes(_graph(), "/repo")
    internal = [e for e in result.edges if e.dst == "module::local.helper"]
    assert internal and internal[0].kind == "imports"


def test_external_non_library_nodes_are_dropped():
    result = synthesize_library_nodes(_graph(), "/repo")
    assert all(not (n.is_external and n.kind != "library") for n in result.nodes)
