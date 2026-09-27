"""The loading Worker answers a request without an access pass as Carl's gate
would (deploy/cloudflare/worker.js), so its copies must match the gate's."""

import re
from pathlib import Path

from carl import gate, server

WORKER = Path(__file__).parents[1] / "deploy" / "cloudflare" / "worker.js"


def test_the_worker_serves_the_gates_own_pass_form():
    path = re.search(r'import PASS_PAGE from "(.+?)"', WORKER.read_text()).group(1)
    assert (WORKER.parent / path).read_text(encoding="utf-8") == server.PASS_PAGE


def test_the_worker_looks_for_the_gates_cookie_and_sends_its_csp():
    source = WORKER.read_text()
    assert f"(?:^|;\\s*){gate.COOKIE}=" in source
    assert f'const PASS_CSP = "{server.PASS_CSP}";' in source
