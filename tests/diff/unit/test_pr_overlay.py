from codegraph.diff.pr_overlay import build_overlay
from codegraph.model.graph import Graph, Node

DIFF = """\
diff --git a/pkg/mod.py b/pkg/mod.py
index 1111111..2222222 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -3,3 +3,4 @@ def run():
     step_one()
-    step_two()
+    step_two(retries=3)
+    step_three()
     return done()
diff --git a/pkg/other.py b/pkg/other.py
index 3333333..4444444 100644
--- a/pkg/other.py
+++ b/pkg/other.py
@@ -1,1 +1,1 @@
-old_line
+new_line
"""


def _graph():
    return Graph(
        nodes=[
            Node(id="pkg/mod.py::run", kind="function", name="run",
                 path="/repo/pkg/mod.py", line_start=2, line_end=8),
            Node(id="pkg/mod.py::unrelated", kind="function", name="unrelated",
                 path="/repo/pkg/mod.py", line_start=20, line_end=30),
        ]
    )


def test_hunk_lines_map_to_symbol_spans():
    # Act
    overlay = build_overlay(_graph(), DIFF, "/repo", base="main", head="HEAD")
    # Assert
    per = {d.symbol_id: d for d in overlay.per_node}
    assert "pkg/mod.py::run" in per
    assert per["pkg/mod.py::run"].added_lines == [4, 5]
    assert per["pkg/mod.py::run"].removed_lines == [4]
    assert "pkg/mod.py::unrelated" not in per


def test_files_without_indexed_symbols_are_reported():
    overlay = build_overlay(_graph(), DIFF, "/repo", base="main", head="HEAD")
    assert overlay.unmapped_files == ["pkg/other.py"]


def test_hunk_text_is_attached_once_per_node():
    overlay = build_overlay(_graph(), DIFF, "/repo", base="main", head="HEAD")
    node = next(d for d in overlay.per_node if d.symbol_id == "pkg/mod.py::run")
    assert len(node.hunks) == 1
    assert "step_three()" in node.hunks[0]
