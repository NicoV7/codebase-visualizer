"""3D city end-to-end: exported HTML boots WebGL, expands, and paints pixels."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

from codegraph.export.city import build_city_data  # noqa: E402
from codegraph.model.graph import Edge, Graph, Node  # noqa: E402

PAPER_RGB = (214, 210, 184)


def _fixture_graph():
    nodes = [
        Node(id="core/logic.py::apply", kind="function", name="apply",
             path="/repo/core/logic.py", line_start=1, line_end=120, complexity=6),
        Node(id="core/logic.py::helper", kind="function", name="helper",
             path="/repo/core/logic.py", line_start=130, line_end=160, complexity=2),
        Node(id="cli/main.py::main", kind="function", name="main",
             path="/repo/cli/main.py", line_start=1, line_end=40),
    ]
    edges = [
        Edge(src="cli/main.py::main", dst="core/logic.py::apply", kind="calls"),
        Edge(src="core/logic.py::apply", dst="core/logic.py::helper", kind="calls"),
    ]
    return Graph(nodes=nodes, edges=edges)


@pytest.fixture(scope="module")
def city_html(tmp_path_factory):
    import json
    from pathlib import Path

    template = Path(__file__).parents[2] / "viz" / "city3d-template.html"
    bundle = Path(__file__).parents[2] / "viz" / "vendor" / "three-bundle.min.js"
    if not bundle.exists():
        pytest.skip("vendor bundle missing - run node scripts/build-vendor.mjs")
    data = build_city_data(_fixture_graph(), "/repo", title="fixture", detail=True)
    payload = json.dumps(data).replace("</", "<\\/")
    html = template.read_text().replace("/*__THREE_BUNDLE__*/", bundle.read_text()).replace(
        "/*__CODEGRAPH_DATA__*/", f"window.CODEGRAPH_DATA = {payload};"
    )
    out = tmp_path_factory.mktemp("city") / "city.html"
    out.write_text(html)
    return out


@pytest.fixture(scope="module")
def page_factory(city_html):
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader"])
        probe = browser.new_page()
        has_webgl = probe.evaluate("!!document.createElement('canvas').getContext('webgl2')")
        probe.close()
        if not has_webgl:
            browser.close()
            pytest.skip("headless chromium has no WebGL2 in this environment")

        def make(fragment=""):
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.errors = []
            page.on("pageerror", lambda e: page.errors.append(str(e)))
            page.goto(f"file://{city_html}{fragment}")
            page.wait_for_function("window.__CITY_READY === true", timeout=20000)
            return page

        yield make
        browser.close()


@pytest.mark.e2e
class TestCity3d:
    def test_boots_and_paints_non_paper_pixels(self, page_factory):
        # Arrange
        page = page_factory()
        page.wait_for_timeout(600)
        # Act: sample the center of the stage canvas
        painted = page.evaluate(
            """() => {
              const cv = document.querySelector('#stage canvas');
              const ctx = document.createElement('canvas').getContext('2d');
              ctx.canvas.width = cv.width; ctx.canvas.height = cv.height;
              ctx.drawImage(cv, 0, 0);
              const px = ctx.getImageData(0, 0, cv.width, cv.height).data;
              let diff = 0;
              for (let i = 0; i < px.length; i += 40) {
                if (Math.abs(px[i] - %d) + Math.abs(px[i+1] - %d) + Math.abs(px[i+2] - %d) > 24) diff++;
              }
              return diff;
            }"""
            % PAPER_RGB
        )
        # Assert: the scene painted something that is not the paper background
        assert painted > 50, "canvas appears blank (all paper-colored)"
        assert page.errors == []

    def test_expand_component_adds_file_entities(self, page_factory):
        page = page_factory()
        before = page.evaluate("window.__city.state().entities")
        page.evaluate("window.__city.expand('core')")
        page.wait_for_timeout(400)
        state = page.evaluate("window.__city.state()")
        assert "core" in state["expanded"]
        assert state["entities"] > before

    def test_expand_file_adds_symbol_entities(self, page_factory):
        page = page_factory()
        page.evaluate("window.__city.expand('core')")
        page.wait_for_timeout(200)
        before = page.evaluate("window.__city.state().entities")
        page.evaluate("window.__city.expandFile('core', 'core/logic.py')")
        page.wait_for_timeout(400)
        state = page.evaluate("window.__city.state()")
        assert "core::core/logic.py" in state["files"]
        assert state["entities"] == before + 2  # apply + helper rise from the file

    def test_hash_preload_expands_component(self, page_factory):
        page = page_factory("#inside=core")
        page.wait_for_timeout(400)
        assert "core" in page.evaluate("window.__city.state().expanded")

    def test_trace_step_selects_component(self, page_factory):
        page = page_factory()
        page.evaluate("window.__city.setTrace(0)")
        page.wait_for_timeout(300)
        assert "1." in page.inner_text("#tracelist .tracestep.on")
        assert page.errors == []
