import asyncio
import re
import time

from carl import gate
from carl.server import WEB

from .conftest import PASSWORD


async def test_health_is_open_and_not_cached(client):
    response = await client.get("/api/health")
    assert response.status == 200
    assert await response.json() == {"ok": True}
    assert response.headers["Cache-Control"] == "no-store, no-transform"


async def test_the_page_asks_for_an_access_pass(client):
    response = await client.get("/")
    assert response.status == 401
    text = await response.text()
    assert '<form method="post" action="/api/unlock">' in text
    assert 'type="password"' in text


async def test_everything_else_is_behind_the_gate(client):
    for path in ["/static/app.js", "/static/style.css", "/static/fonts/OFL.txt", "/nowhere"]:
        response = await client.get(path)
        assert response.status == 401, path
        assert "action=\"/api/unlock\"" in await response.text()
    for path in ["/api/ws", "/api/anything"]:
        assert (await client.get(path)).status == 401, path
    assert (await client.post("/api/anything")).status == 401


async def test_a_correct_pass_sets_the_cookie(client, passes):
    response = await client.post("/api/unlock", data={"pass": f" {PASSWORD} "}, allow_redirects=False)
    assert response.status == 303
    assert response.headers["Location"] == "/"
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith(f"{gate.COOKIE}={passes.token(passes.check(PASSWORD))};")
    for attribute in ["HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=31536000"]:
        assert attribute in cookie


async def test_a_wrong_pass_waits_a_second(client):
    start = time.monotonic()
    response = await client.post("/api/unlock", data={"pass": "bakodi-sulema-rotike-fanupb"})
    assert time.monotonic() - start >= 1
    assert response.status == 401
    assert "didn’t work" in await response.text()
    assert "Set-Cookie" not in response.headers
    assert (await client.get("/")).status == 401


async def test_wrong_passes_do_not_wait_in_line(client, monkeypatch):
    """The 1 s wait is no lockout: each answer takes about 1 s, however many arrive."""
    monkeypatch.setattr(gate, "WRONG_PASS_WAIT_S", 0.5)
    start = time.monotonic()
    responses = await asyncio.gather(*(client.post("/api/unlock", data={"pass": "wrong-pass-12"}) for _ in range(5)))
    assert all(r.status == 401 for r in responses)
    assert time.monotonic() - start < 2


async def test_the_cookie_opens_the_page(unlocked):
    response = await unlocked.get("/")
    assert response.status == 200
    assert "<title>Carl</title>" in await response.text()
    for path in ["/static/app.js", "/static/link.js", "/static/style.css"]:
        assert (await unlocked.get(path)).status == 200, path


async def test_nothing_behind_the_gate_is_kept_in_a_shared_cache(unlocked):
    for path in ["/", "/static/app.js", "/static/fonts/atkinson-hyperlegible-latin-400-normal.woff2"]:
        cache = (await unlocked.get(path)).headers["Cache-Control"]
        assert cache == "private, no-cache, no-transform", path
    unlocked.session.cookie_jar.clear()
    response = await unlocked.get("/")
    assert response.status == 401
    assert response.headers["Cache-Control"] == "no-store, no-transform"


async def test_a_forged_cookie_does_not(client):
    client.session.cookie_jar.update_cookies({gate.COOKIE: "0" * 64})
    assert (await client.get("/")).status == 401


async def test_the_page_allows_no_third_party_calls(unlocked):
    policy = (await unlocked.get("/")).headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "http" not in policy


def test_the_page_names_no_other_origin():
    for path in WEB.rglob("*"):
        if path.suffix in {".html", ".css", ".js"}:
            assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", path.read_text()), path


def test_the_page_links_only_files_that_exist():
    for path in WEB.rglob("*"):
        if path.suffix in {".html", ".css", ".js"}:
            for link in re.findall(r"""(?:href|src)="/static/([^"]+)"|url\(([^)]+)\)|from "\./([^"]+)\"""", path.read_text()):
                target = next(filter(None, link))
                assert (WEB / target).is_file() or (path.parent / target).is_file(), (path, target)
