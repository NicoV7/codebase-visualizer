from codegraph.export.isometric import build_isometric_data, component_of
from codegraph.model.graph import Edge, Graph, Node


def _graph():
    return Graph(
        nodes=[
            Node(id="cli/main.py::run", kind="function", name="run",
                 path="/repo/cli/main.py", line_start=1, line_end=40),
            Node(id="core/logic.py::apply", kind="function", name="apply",
                 path="/repo/core/logic.py", line_start=1, line_end=200),
            Node(id="lib::sample_pkg", kind="library", name="sample_pkg", is_external=True),
        ],
        edges=[
            Edge(src="cli/main.py::run", dst="core/logic.py::apply", kind="calls"),
            Edge(src="core/logic.py::apply", dst="lib::sample_pkg", kind="uses_library"),
        ],
    )


def test_components_aggregate_by_directory():
    data = build_isometric_data(_graph(), "/repo", title="t")
    ids = {s["id"] for s in data["structures"]}
    assert {"cli", "core", "lib/sample_pkg"} <= ids


def test_zones_and_heights_scale_with_loc():
    data = build_isometric_data(_graph(), "/repo", title="t")
    by_id = {s["id"]: s for s in data["structures"]}
    assert by_id["cli"]["zone"] == "entry"
    assert by_id["lib/sample_pkg"]["zone"] == "external"
    assert by_id["core"]["h"] >= by_id["cli"]["h"]


def test_trace_starts_at_entry_and_prefers_internal():
    data = build_isometric_data(_graph(), "/repo", title="t")
    steps = [s["structure"] for s in data["trace"]]
    assert steps[0] == "cli"
    assert steps[1] == "core"


def test_scrub_removes_sensitive_strings():
    graph = _graph()
    graph.nodes[0].path = "/repo/cli/secret_token_loader.py"
    data = build_isometric_data(graph, "/repo", title="t", scrub=True)
    assert "secret" not in str(data).lower() or "[scrubbed]" in str(data)


def test_component_of_handles_shallow_paths():
    assert component_of("/repo/single.py", "/repo") == "single.py"
    assert component_of("/elsewhere/x.py", "/repo") is None
