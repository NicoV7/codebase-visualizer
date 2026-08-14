import json
import urllib.request

import pytest

from codegraph.review.server import ReviewServer


class FakeService:
    def __init__(self):
        self.marks = []

    def comprehension(self):
        return {"states": {}, "percent": 12.5, "counts": {"unreviewed": 7, "walked": 1, "owned": 0}, "unreviewed": []}

    def mark_understood(self, symbol_id, state="walked"):
        if state not in ("walked", "owned"):
            raise ValueError(f"bad state {state}")
        self.marks.append((symbol_id, state))


@pytest.fixture
def server():
    svc = FakeService()
    srv = ReviewServer(svc, "<html>city</html>", port=0)
    srv.serve_background()
    yield srv, svc
    srv.shutdown()


def _post(url, payload, headers=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class TestReviewServer:
    def test_serves_city_html(self, server):
        srv, _ = server
        with urllib.request.urlopen(srv.url) as resp:
            assert resp.status == 200
            assert b"city" in resp.read()

    def test_post_marks_and_returns_updated_comprehension(self, server):
        srv, svc = server
        status, body = _post(srv.url + "api/understanding",
                             {"symbol_id": "a::f", "state": "owned"}, {"X-Codegraph": "1"})
        assert status == 200
        assert body["percent"] == 12.5
        assert svc.marks == [("a::f", "owned")]

    def test_post_without_custom_header_is_rejected(self, server):
        srv, svc = server
        status, _ = _post(srv.url + "api/understanding", {"symbol_id": "a::f"})
        assert status == 403
        assert svc.marks == []

    def test_bad_state_is_400(self, server):
        srv, _ = server
        status, _ = _post(srv.url + "api/understanding",
                          {"symbol_id": "a::f", "state": "vibes"}, {"X-Codegraph": "1"})
        assert status == 400

    def test_bad_host_header_is_rejected(self, server):
        srv, _ = server
        req = urllib.request.Request(srv.url, headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 421
