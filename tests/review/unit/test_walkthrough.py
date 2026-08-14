from codegraph.diff.pr_overlay import DiffOverlay, NodeDiff
from codegraph.model.graph import Edge, Graph, Node
from codegraph.overlay.descriptions import Description
from codegraph.overlay.reasons import Reason
from codegraph.review.walkthrough import MAX_SNIPPET_LINES, build_walkthrough


def _graph(tmp_path):
    src = tmp_path / "cli" / "main.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("\n".join(f"line {i}" for i in range(1, 200)))
    core = tmp_path / "core" / "logic.py"
    core.parent.mkdir(parents=True, exist_ok=True)
    core.write_text("\n".join(f"logic {i}" for i in range(1, 60)))
    return Graph(
        nodes=[
            Node(id="cli/main.py::main", kind="function", name="main",
                 path=str(src), line_start=1, line_end=20),
            Node(id="core/logic.py::apply", kind="function", name="apply",
                 path=str(core), line_start=1, line_end=30),
            Node(id="core/logic.py::helper", kind="function", name="helper",
                 path=str(core), line_start=35, line_end=50),
        ],
        edges=[
            Edge(src="cli/main.py::main", dst="core/logic.py::apply", kind="calls"),
            Edge(src="core/logic.py::apply", dst="core/logic.py::helper", kind="calls"),
        ],
    )


def _diff(*sids):
    return DiffOverlay(
        base="main", head="HEAD",
        per_node=[NodeDiff(symbol_id=s, added_lines=[2], removed_lines=[], hunks=["@@ hunk @@"]) for s in sids],
    )


class TestWalkthrough:
    def test_entry_zone_symbol_comes_first_in_execution_order(self, tmp_path):
        # Act
        wt = build_walkthrough(
            _graph(tmp_path), str(tmp_path),
            _diff("cli/main.py::main", "core/logic.py::apply", "core/logic.py::helper"),
            {}, [], {}, scope="diff",
        )
        # Assert
        order = [s["symbol_id"] for s in wt["stops"] if s["kind"] == "changed"]
        assert order == ["cli/main.py::main", "core/logic.py::apply", "core/logic.py::helper"]

    def test_deterministic_across_builds(self, tmp_path):
        args = (
            _graph(tmp_path), str(tmp_path),
            _diff("core/logic.py::apply", "core/logic.py::helper"), {}, [], {},
        )
        a = build_walkthrough(*args, scope="diff")
        b = build_walkthrough(*args, scope="diff")
        a.pop("generated_at"); b.pop("generated_at")
        assert a == b

    def test_cycle_broken_deterministically(self, tmp_path):
        graph = _graph(tmp_path)
        graph.edges.append(Edge(src="core/logic.py::helper", dst="core/logic.py::apply", kind="calls"))
        wt = build_walkthrough(
            graph, str(tmp_path), _diff("core/logic.py::apply", "core/logic.py::helper"),
            {}, [], {}, scope="diff",
        )
        order = [s["symbol_id"] for s in wt["stops"] if s["kind"] == "changed"]
        assert order == ["core/logic.py::apply", "core/logic.py::helper"]

    def test_unchanged_caller_becomes_context_stop(self, tmp_path):
        wt = build_walkthrough(
            _graph(tmp_path), str(tmp_path), _diff("core/logic.py::apply"),
            {}, [], {}, scope="diff",
        )
        context = [s for s in wt["stops"] if s["kind"] == "context"]
        assert [s["symbol_id"] for s in context] == ["cli/main.py::main"]
        assert context[0]["context_for"] == ["core/logic.py::apply"]

    def test_missing_description_is_an_explicit_gap(self, tmp_path):
        descs = {"core/logic.py::apply": Description(symbol_id="core/logic.py::apply", body="Applies rules.")}
        wt = build_walkthrough(
            _graph(tmp_path), str(tmp_path),
            _diff("core/logic.py::apply", "core/logic.py::helper"), descs, [], {}, scope="diff",
        )
        by_sid = {s["symbol_id"]: s for s in wt["stops"]}
        assert by_sid["core/logic.py::apply"]["gap"] is False
        assert by_sid["core/logic.py::helper"]["gap"] is True

    def test_snippet_read_from_file_with_cap_totals(self, tmp_path):
        graph = _graph(tmp_path)
        graph.nodes[0].line_end = 150  # longer than the snippet cap
        wt = build_walkthrough(
            graph, str(tmp_path), _diff("cli/main.py::main"), {}, [], {}, scope="diff",
        )
        snippet = wt["stops"][0]["snippet"]
        assert snippet["lines"][0] == "line 1"
        assert snippet["shown"] == MAX_SNIPPET_LINES
        assert snippet["total"] == 150
        assert snippet["truncated"] is True

    def test_trace_path_runs_entry_to_stop_with_files_and_lines(self, tmp_path):
        # Act
        wt = build_walkthrough(
            _graph(tmp_path), str(tmp_path), _diff("core/logic.py::helper"),
            {}, [], {}, scope="diff",
        )
        # Assert: entry (main) -> apply -> helper, each hop mapped to file:line
        stop = wt["stops"][0]
        hops = stop["trace_path"]
        assert [h["symbol_id"] for h in hops] == [
            "cli/main.py::main", "core/logic.py::apply", "core/logic.py::helper",
        ]
        assert hops[0]["file"] == "cli/main.py" and hops[0]["line"] == 1
        assert hops[2]["file"] == "core/logic.py" and hops[2]["line"] == 35
        assert stop["trace_path_total"] == 3

    def test_symbol_without_callers_is_its_own_path(self, tmp_path):
        wt = build_walkthrough(
            _graph(tmp_path), str(tmp_path), _diff("cli/main.py::main"),
            {}, [], {}, scope="diff",
        )
        assert [h["symbol_id"] for h in wt["stops"][0]["trace_path"]] == ["cli/main.py::main"]

    def test_reasons_and_understanding_ride_on_stops(self, tmp_path):
        wt = build_walkthrough(
            _graph(tmp_path), str(tmp_path), _diff("core/logic.py::apply"),
            {}, [Reason(symbol_id="core/logic.py::apply", why="retries were masking outages", kind="changed")],
            {"core/logic.py::apply": "walked"}, scope="diff",
        )
        stop = wt["stops"][0]
        assert stop["reasons"][0]["why"] == "retries were masking outages"
        assert stop["understanding"] == "walked"
