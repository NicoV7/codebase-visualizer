"""Review mode e2e: player advances, got-it persists, heatmap reacts."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

from codegraph.diff.pr_overlay import DiffOverlay, NodeDiff  # noqa: E402
from codegraph.model.graph import Edge, Graph, Node  # noqa: E402
from codegraph.overlay.understanding import UnderstandingLedger  # noqa: E402
from codegraph.review.server import ReviewServer  # noqa: E402
from codegraph.review.walkthrough import build_walkthrough  # noqa: E402


def _make_repo(tmp_path):
    core = tmp_path / "core" / "logic.py"
    core.parent.mkdir(parents=True)
    core.write_text("\n".join(f"logic {i}" for i in range(1, 60)))
    graph = Graph(
        nodes=[
            Node(id="core/logic.py::apply", kind="function", name="apply",
                 path=str(core), line_start=1, line_end=30),
            Node(id="core/logic.py::helper", kind="function", name="helper",
                 path=str(core), line_start=35, line_end=50),
        ],
        edges=[Edge(src="core/logic.py::apply", dst="core/logic.py::helper", kind="calls")],
    )
    diff = DiffOverlay(base="main", head="HEAD", per_node=[
        NodeDiff(symbol_id="core/logic.py::apply", added_lines=[2, 3], removed_lines=[], hunks=["@@ h @@"]),
        NodeDiff(symbol_id="core/logic.py::helper", added_lines=[36], removed_lines=[], hunks=["@@ h2 @@"]),
    ])
    return graph, diff


class ServiceStub:
    """Real ledger + real hashes over the fixture repo; no engine."""

    def __init__(self, tmp_path, graph):
        self.project_root = str(tmp_path)
        self.graph_obj = graph
        self.understanding = UnderstandingLedger(tmp_path)

    def _hashes(self):
        from codegraph.overlay.descriptions import content_hash
        from pathlib import Path

        out = {}
        for n in self.graph_obj.nodes:
            lines = Path(n.path).read_text().splitlines()
            out[n.id] = content_hash("\n".join(lines[n.line_start - 1 : n.line_end]))
        return out

    def mark_understood(self, symbol_id, state="walked"):
        from codegraph.overlay.understanding import UnderstandingEntry

        return self.understanding.record(
            UnderstandingEntry(symbol_id=symbol_id, state=state,
                               hash_at_review=self._hashes().get(symbol_id))
        )

    def comprehension(self):
        states = self.understanding.effective(self._hashes())
        nodes = self.graph_obj.nodes
        loc = {n.id: n.line_end - n.line_start + 1 for n in nodes}
        total = sum(loc.values())
        understood = sum(loc.get(s, 0) for s in states)
        return {
            "states": states,
            "percent": round(100 * understood / total, 1),
            "counts": {"unreviewed": len(nodes) - len(states),
                       "walked": sum(1 for v in states.values() if v == "walked"),
                       "owned": sum(1 for v in states.values() if v == "owned")},
            "unreviewed": sorted(n.id for n in nodes if n.id not in states),
        }


def _render_html(tmp_path, graph, diff, served):
    from pathlib import Path

    from codegraph.export.city import build_city_data

    template = Path(__file__).parents[2] / "viz" / "city3d-template.html"
    bundle = Path(__file__).parents[2] / "viz" / "vendor" / "three-bundle.min.js"
    if not bundle.exists():
        pytest.skip("vendor bundle missing")
    wt = build_walkthrough(graph, str(tmp_path), diff, {}, [], {}, scope="diff")
    data = build_city_data(graph, str(tmp_path), title="fixture", detail=True)
    data["review"] = {
        "understanding": {"states": {}, "percent": 0.0,
                          "counts": {"unreviewed": 2, "walked": 0, "owned": 0}, "unreviewed": []},
        "served": served,
        "walkthrough": wt,
    }
    payload = json.dumps(data).replace("</", "<\\/")
    return template.read_text().replace("/*__THREE_BUNDLE__*/", bundle.read_text()).replace(
        "/*__CODEGRAPH_DATA__*/", f"window.CODEGRAPH_DATA = {payload};"
    )


@pytest.mark.e2e
class TestReviewMode:
    def test_served_walkthrough_advances_and_persists(self, tmp_path):
        graph, diff = _make_repo(tmp_path)
        service = ServiceStub(tmp_path, graph)
        server = ReviewServer(service, _render_html(tmp_path, graph, diff, served=True))
        server.serve_background()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(args=["--use-angle=swiftshader"])
                page = browser.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.goto(server.url)
                page.wait_for_function("window.__CITY_READY === true", timeout=20000)
                # Player boots on stop 1; apply (entry of the changed subgraph) first
                state = page.evaluate("window.__city.reviewState()")
                assert state == {"stop": 1, "total": 2, "inTour": True}
                assert "apply" in page.inner_text("#panel h2")
                # got it: persists to the ledger and advances
                page.evaluate("window.__city.reviewGotIt()")
                page.wait_for_timeout(500)
                assert page.evaluate("window.__city.reviewState()")["stop"] == 2
                assert page.evaluate("window.__city.understandingOf('core/logic.py::apply')") == "walked"
                # the route is visible and every hop has a station
                trace = page.evaluate("window.__city.tracePath()")
                assert trace["visible"] and trace["hops"] >= 2
                assert trace["stations"] == trace["hops"]
                # reset clears the route
                page.click("#btn-reset")
                page.wait_for_timeout(200)
                assert page.evaluate("window.__city.tracePath()")["visible"] is False
                assert page.evaluate("window.__city.percentUnderstood()") > 0
                ledger = (tmp_path / ".codegraph" / "understanding.jsonl").read_text()
                assert "core/logic.py::apply" in ledger
                assert errs == []
                browser.close()
        finally:
            server.shutdown()

    def test_static_export_disables_got_it(self, tmp_path):
        graph, diff = _make_repo(tmp_path)
        out = tmp_path / "city.html"
        out.write_text(_render_html(tmp_path, graph, diff, served=False))
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-angle=swiftshader"])
            page = browser.new_page()
            page.goto(f"file://{out}")
            page.wait_for_function("window.__CITY_READY === true", timeout=20000)
            assert page.is_disabled("#rv-gotit")
            assert "static export" in page.inner_text("#panel")
            browser.close()
