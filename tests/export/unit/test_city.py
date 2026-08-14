from codegraph.export.city import (
    MAX_SYMBOLS_PER_FILE,
    build_city_data,
)
from codegraph.model.graph import Edge, Graph, Node


def _graph():
    return Graph(
        nodes=[
            Node(id="core/logic.py::apply", kind="function", name="apply",
                 path="/repo/core/logic.py", line_start=1, line_end=60, complexity=4),
            Node(id="core/logic.py::helper", kind="function", name="helper",
                 path="/repo/core/logic.py", line_start=70, line_end=90, complexity=1),
            Node(id="core/other.py::run", kind="function", name="run",
                 path="/repo/core/other.py", line_start=1, line_end=30),
            Node(id="cli/main.py::main", kind="function", name="main",
                 path="/repo/cli/main.py", line_start=1, line_end=20),
        ],
        edges=[
            Edge(src="core/logic.py::apply", dst="core/logic.py::helper", kind="calls"),
            Edge(src="cli/main.py::main", dst="core/logic.py::apply", kind="calls"),
        ],
    )


class TestDetailPayload:
    def test_children_group_symbols_by_file_with_loc(self):
        # Act
        data = build_city_data(_graph(), "/repo", title="t", detail=True)
        # Assert
        core = next(s for s in data["structures"] if s["id"] == "core")
        files = {f["path"]: f for f in core["children"]["files"]}
        assert files["core/logic.py"]["loc"] == 60 + 21
        assert [s["name"] for s in files["core/logic.py"]["symbols"]] == ["apply", "helper"]
        assert files["core/logic.py"]["symbols"][0]["complexity"] == 4

    def test_intra_component_call_edge_survives_in_symbol_edges(self):
        data = build_city_data(_graph(), "/repo", title="t", detail=True)
        idx = data["symbol_index"]
        pairs = {(idx[s], idx[d]) for s, d, _ in data["symbol_edges"]}
        assert ("core/logic.py::apply", "core/logic.py::helper") in pairs

    def test_cross_component_symbol_edge_present(self):
        data = build_city_data(_graph(), "/repo", title="t", detail=True)
        idx = data["symbol_index"]
        pairs = {(idx[s], idx[d]) for s, d, _ in data["symbol_edges"]}
        assert ("cli/main.py::main", "core/logic.py::apply") in pairs

    def test_symbol_index_resolves_children_indices(self):
        data = build_city_data(_graph(), "/repo", title="t", detail=True)
        idx = data["symbol_index"]
        for structure in data["structures"]:
            for f in structure["children"]["files"]:
                for sym in f["symbols"]:
                    assert idx[sym["i"]].endswith(sym["name"])

    def test_caps_report_totals_not_silence(self):
        # Arrange: one file with more symbols than the per-file cap
        nodes = [
            Node(id=f"big/blob.py::f{i}", kind="function", name=f"f{i}",
                 path="/repo/big/blob.py", line_start=i * 10, line_end=i * 10 + 5)
            for i in range(MAX_SYMBOLS_PER_FILE + 15)
        ]
        data = build_city_data(Graph(nodes=nodes), "/repo", title="t", detail=True)
        # Assert
        big = next(s for s in data["structures"] if s["id"] == "big")
        blob = big["children"]["files"][0]
        assert len(blob["symbols"]) == MAX_SYMBOLS_PER_FILE
        assert blob["symbols_total"] == MAX_SYMBOLS_PER_FILE + 15
        assert big["children"]["truncated"] is True

    def test_detail_false_omits_detail_fields(self):
        data = build_city_data(_graph(), "/repo", title="t", detail=False)
        assert "symbol_index" not in data
        assert "children" not in data["structures"][0]

    def test_deterministic_output(self):
        assert build_city_data(_graph(), "/repo", title="t", detail=True) == build_city_data(
            _graph(), "/repo", title="t", detail=True
        )

    def test_scrub_applies_to_detail_payload(self):
        graph = _graph()
        graph.nodes[0].path = "/repo/core/secret_token_logic.py"
        graph.nodes[0].id = "core/secret_token_logic.py::apply"
        data = build_city_data(graph, "/repo", title="t", detail=True, scrub=True)
        assert "secret" not in str(data).lower() or "[scrubbed]" in str(data)
