import asyncio
import dataclasses
import itertools
import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from aiohttp import web

from carl.checking import (
    ANSWERED, CLAIM_RIGHT, CLAIM_WRONG, COMPATIBLE, CONTRADICT, DOESNT_ANSWER, MAX_PAGE_BYTES, MIN_EXCERPT_CHARS,
    MIN_EXCERPT_WORDS, NOT_FOUND, NOT_SUPPORTED, REASONS, SAME_FACT, SUPPORTED, UNREADABLE, Agreement, Band, Judged,
    PrivateAddress, band_pair, band_single, blocklisted, card_words, download_client, find_excerpt, hedged_fact,
    normalize, page_match, page_text, refuse_private, same_page, snippet_match,
)
from carl.config import Bands

# The spec's starting thresholds (section 13), as in config.toml.
BANDS = Bands(plain_same_fact=0.7, plain_supported_shown=0.85, plain_supported_other=0.5, hedged_supported=0.6)


# --- Normalising and matching text ------------------------------------------------


def test_whitespace_is_collapsed_including_non_breaking_and_thin_spaces():
    assert normalize("  Helsingissä\n\tasuu \u00a0noin\u202f680\u2009000   ihmistä. ") == \
        "Helsingissä asuu noin 680 000 ihmistä."


def test_soft_hyphens_and_zero_width_characters_are_removed():
    assert normalize("Kansallis\u00adteatteri") == "Kansallisteatteri"
    assert normalize("\ufeffCasa\u200bblanca\u2060") == "Casablanca"


def test_quotation_marks_and_apostrophes_are_one_mark():
    straight = normalize("He said \"Here's looking at you, kid.\"")
    assert normalize("He said “Here’s looking at you, kid.”") == straight
    assert normalize("He said „Here‘s looking at you, kid.“") == straight
    assert normalize("He said «Here´s looking at you, kid.»") == straight
    assert normalize("Hän sanoi: ”Täällä ollaan.”") == normalize('Hän sanoi: "Täällä ollaan."')
    assert normalize("»Tuntematon sotilas«") == normalize("'Tuntematon sotilas'")


def test_dashes_and_the_minus_sign_are_a_hyphen():
    assert normalize("vuosina 1939–1945") == "vuosina 1939-1945"
    assert normalize("Talvisota — ja jatkosota") == "Talvisota - ja jatkosota"
    assert normalize("−40 °C") == "-40 °C"


def test_unicode_is_composed_and_case_is_kept():
    assert normalize("Ha\u0308n on Mo\u0308tto\u0308nen") == "Hän on Möttönen"
    assert normalize("Helsinki") != normalize("helsinki")


def test_an_ellipsis_is_three_dots():
    assert normalize("and so on…") == "and so on..."


def test_an_excerpt_is_found_after_normalising_both_sides():
    page = "Casablanca is a 1942 American romantic drama film directed by\u00a0Michael Curtiz."
    assert find_excerpt("Casablanca is a 1942 American romantic drama film directed by Michael Curtiz", page) \
        == "normalised"
    page = "Lindstro\u0308m kertoi, että \"pääkaupunki on Helsinki\"."
    assert find_excerpt("Lindström kertoi, että ”pääkaupunki on Helsinki”", page) == "normalised"


def test_matching_is_case_sensitive():
    assert find_excerpt("casablanca is a 1942 film", "Casablanca is a 1942 film") is None


def test_quotation_marks_and_ellipses_at_the_excerpts_ends_are_trimmed():
    page = "Bogart played Rick Blaine, an American expatriate."
    assert find_excerpt("“Bogart played Rick Blaine…”", page) == "normalised"
    assert find_excerpt('..."Bogart played Rick Blaine"...', page) == "normalised"
    assert find_excerpt("Bogart played Rick Blaine.", page) is None  # a period isn't trimmed


def test_an_empty_excerpt_never_matches():
    assert find_excerpt("", "anything") is None
    assert find_excerpt(" “ ” … ", "anything") is None


def test_a_short_excerpt_never_matches():
    page = "Näytös oli Kansallisteatterissa Helsingissä vuonna 1952."
    assert find_excerpt("1952", page) is None
    assert find_excerpt("Kansallisteatterissa Helsingissä", page) is None  # 32 characters, but 2 words
    assert find_excerpt("“vuonna 1952”", page) is None  # the trimmed quotation marks don't count
    assert find_excerpt("Helsingissä vuonna 1952", page) == "normalised"


def test_the_shortest_excerpt_is_20_characters_and_3_words():
    assert (MIN_EXCERPT_CHARS, MIN_EXCERPT_WORDS) == (20, 3)
    page = "Ilsa Lund on Bergman, ei Ingrid Rick."
    assert len("Ilsa Lund on Bergman") == 20 and find_excerpt("Ilsa Lund on Bergman", page) == "normalised"
    assert len("Lund on Bergman, ei") == 19 and find_excerpt("Lund on Bergman, ei", page) is None
    assert find_excerpt("  Ilsa   Lund on\u00a0Bergman ", page) == "normalised"  # measured after normalising


def test_an_excerpt_glued_from_two_table_cells_matches_without_spaces():
    page = page_text("<table><tr><td>Humphrey Bogart</td><td>Rick Blaine</td></tr></table>")
    assert "Humphrey Bogart\n" in page and "BogartRick" not in page
    assert find_excerpt("Humphrey Bogart Rick Blaine", page) == "normalised"
    assert find_excerpt("Humphrey BogartRick Blaine", page) == "spaceless"
    # A spaced excerpt of text the page itself runs together matches too.
    glued = page_text("<span>Humphrey Bogart</span><span>Rick Blaine</span>")
    assert find_excerpt("Humphrey Bogart Rick Blaine", glued) == "spaceless"
    # Only spacing may differ.
    assert find_excerpt("Humphrey BogartRick Blain e.", page) is None
    assert find_excerpt("Humphrey Bogart as Rick Blaine", page) is None


# --- The page's text -------------------------------------------------------------------


def test_page_text_leaves_out_scripts_styles_and_templates():
    html = """<html><head><title>Casablanca</title><style>p { color: red }</style>
    <script>var cast = "Ronald Reagan as Rick";</script></head>
    <body><p>Rick is played by <a href="/b">Humphrey</a> <b>Bog</b>art.</p>
    <template><p>Ronald Reagan</p></template><!-- Ronald Reagan --></body></html>"""
    text = page_text(html)
    assert "Ronald Reagan" not in text and "color" not in text
    assert find_excerpt("Rick is played by Humphrey Bogart.", text) == "normalised"


def test_block_elements_are_kept_apart_and_entities_decoded():
    html = ("<ul><li>Ingrid Bergman</li><li>Paul Henreid</li></ul><p>Here&rsquo;s&nbsp;looking</p>"
            "<div>Kansallis&shy;teatteri</div>line one<br>line two")
    text = normalize(page_text(html))
    assert text == "Ingrid Bergman Paul Henreid Here's looking Kansallisteatteri line one line two"


# --- URLs --------------------------------------------------------------------------------


@pytest.mark.parametrize("other", [
    "https://en.wikipedia.org/wiki/Casablanca_(film)",
    "http://en.wikipedia.org/wiki/Casablanca_(film)",
    "HTTPS://EN.Wikipedia.ORG/wiki/Casablanca_(film)",
    "https://en.wikipedia.org./wiki/Casablanca_(film)/",
    "https://en.wikipedia.org:443/wiki/Casablanca_(film)#Cast",
    "https://en.wikipedia.org/wiki/Casablanca_%28film%29",
    "https://en.wikipedia.org/wiki/Casablanca_(film)?utm_source=openai",
    " https://en.wikipedia.org/wiki/Casablanca_(film) ",
])
def test_the_same_page_under_another_spelling(other):
    assert same_page("https://en.wikipedia.org/wiki/Casablanca_(film)", other)


def test_www_query_order_and_percent_encoding_dont_matter():
    assert same_page("https://www.stat.fi/til/vaerak?a=1&b=2", "https://stat.fi/til/vaerak/?b=2&a=1")
    assert same_page("https://fi.wikipedia.org/wiki/J%C3%A4rvenp%C3%A4%C3%A4",
                     "https://fi.wikipedia.org/wiki/Järvenpää")


@pytest.mark.parametrize("other", [
    "https://en.m.wikipedia.org/wiki/Casablanca_(film)",
    "https://fi.wikipedia.org/wiki/Casablanca_(film)",
    "https://en.wikipedia.org/wiki/casablanca_(film)",
    "https://en.wikipedia.org/wiki/Casablanca",
    "https://en.wikipedia.org/wiki/Casablanca_(film)?oldid=1",
    "https://en.wikipedia.org:8443/wiki/Casablanca_(film)",
    "ftp://en.wikipedia.org/wiki/Casablanca_(film)",
    "not a url",
    "",
])
def test_not_the_same_page(other):
    assert not same_page("https://en.wikipedia.org/wiki/Casablanca_(film)", other)


def test_unreadable_urls_are_never_the_same_page():
    assert not same_page("", "")
    assert not same_page("http://[::1", "http://[::1")


# --- Fact-finder B: the snippet ----------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Result:
    url: str
    title: str
    snippet: str | None


CASABLANCA = "https://en.wikipedia.org/wiki/Casablanca_(film)"
RESULTS = [
    Result("https://www.imdb.com/title/tt0034583/", "Casablanca (1942)", "Ronald Reagan was never cast as Rick."),
    Result(CASABLANCA + "#Cast", "Casablanca (film)",
           "The film stars Humphrey\u00a0Bogart as Rick Blaine, a “cynical” expatriate."),
    Result(CASABLANCA, "Casablanca (film)", None),
]


def test_an_excerpt_in_a_snippet_from_the_same_url_is_verified():
    excerpt = 'Humphrey Bogart as Rick Blaine, a "cynical" expatriate'
    assert snippet_match(excerpt, "http://en.wikipedia.org/wiki/Casablanca_(film)/", RESULTS)


def test_an_excerpt_in_a_snippet_from_another_url_is_not():
    assert not snippet_match("Ronald Reagan was never cast as Rick", CASABLANCA, RESULTS)
    assert not snippet_match("Humphrey Bogart as Rick Blaine", "https://www.imdb.com/title/tt0034583/", RESULTS)


def test_an_excerpt_the_snippet_doesnt_hold_is_not():
    assert not snippet_match("Humphrey Bogart as Rick Blaine, a cynical nightclub owner", CASABLANCA, RESULTS)
    assert not snippet_match("Humphrey Bogart as Rick Blaine", CASABLANCA, [])
    assert not snippet_match("", CASABLANCA, RESULTS)
    assert not snippet_match("Humphrey Bogart as Rick Blaine", "not a url", RESULTS)


def test_a_short_excerpt_in_the_snippet_is_not():
    assert not snippet_match("Rick Blaine", CASABLANCA, RESULTS)
    assert not snippet_match("“Humphrey Bogart”", CASABLANCA, RESULTS)


def test_any_object_with_a_url_and_a_snippet_will_do():
    results = [SimpleNamespace(url="https://yle.fi/a/74-2000", snippet="Presidentti Stubb aloitti kautensa 1.3.2024.")]
    assert snippet_match("Stubb aloitti kautensa 1.3.2024", "https://yle.fi/a/74-2000", results)


# --- The blocklist ---------------------------------------------------------------------


def test_a_suffix_blocks_its_domain_and_subdomains(config):
    suffixes = config.sources.blocklist
    assert blocklisted("https://reddit.com/r/Finland", suffixes) == "reddit.com"
    assert blocklisted("https://old.reddit.com/r/Finland/comments/x", suffixes) == "reddit.com"
    assert blocklisted("https://WWW.Reddit.COM./r/x", suffixes) == "reddit.com"
    assert blocklisted("https://user@m.youtube.com:443/watch?v=x", suffixes) == "youtube.com"
    assert blocklisted("https://keskustelu.suomi24.fi/t/1", suffixes) == "suomi24.fi"
    assert blocklisted("https://x.com/yle", suffixes) == "x.com"


def test_a_suffix_doesnt_block_other_domains_that_end_the_same(config):
    suffixes = config.sources.blocklist
    assert blocklisted("https://notreddit.com/r/x", suffixes) is None
    assert blocklisted("https://www.dropbox.com/s/x", suffixes) is None  # ends in x.com, isn't under it
    assert blocklisted("https://reddit.com.example.org/r/x", suffixes) is None
    assert blocklisted("https://fi.wikipedia.org/wiki/Reddit", suffixes) is None
    assert blocklisted("https://example.org/?u=https://reddit.com/", suffixes) is None


def test_suffixes_are_matched_whatever_their_case_and_dots():
    assert blocklisted("https://www.quora.com/x", [".Quora.COM."]) == ".Quora.COM."
    assert blocklisted("https://quora.com/x", ["", "."]) is None


@pytest.mark.parametrize("url", ["", "not a url", "javascript:alert(1)", "ftp://example.org/x", "https://",
                                 "http://[::1", "mailto:someone@example.org"])
def test_an_unreadable_url_counts_as_blocklisted(url):
    assert blocklisted(url, ["reddit.com"]) == UNREADABLE


# --- Fact-finder A: the page -----------------------------------------------------------

CAST_PAGE = """<!doctype html><html><head><title>Casablanca (1942)</title>
<script>document.write("Ronald Reagan as Rick Blaine");</script><style>td { padding: 0 }</style></head>
<body><h1>Casablanca</h1><p>Directed by <a href="/curtiz">Michael Curtiz</a>&nbsp;&ndash; a “romantic drama”.</p>
<table><tr><th>Actor</th><th>Role</th></tr>
<tr><td>Humphrey Bogart</td><td>Rick Blaine</td></tr><tr><td>Ingrid Bergman</td><td>Ilsa Lund</td></tr></table>
</body></html>"""
BOGART = "Humphrey Bogart Rick Blaine"  # on the cast page, across two table cells
LATIN1 = "<html><body><p>Pietarsaaren väkiluku on noin 19 000.</p></body></html>"
BIG_START = "Alussa oli suo, kuokka ja Jussi."
BIG_END = "Tämä lause on sivun lopussa."


class Site:
    """The local server's address for a path, and the paths it was asked for."""

    def __init__(self, server) -> None:
        self.server, self.hits = server, []

    def __call__(self, path: str) -> str:
        return str(self.server.make_url(path))


@pytest.fixture
async def site(aiohttp_server) -> Site:
    """A local web server with the pages the tests download."""

    async def page(request, body=CAST_PAGE, content_type="text/html", charset="utf-8", status=200):
        return web.Response(text=body, content_type=content_type, charset=charset, status=status)

    async def slow(request):
        await asyncio.sleep(1)
        return web.Response(text=CAST_PAGE, content_type="text/html")

    async def slow_body(request):
        """A chunk every 0.15 s: each read is quick, the whole takes 0.9 s."""
        response = web.StreamResponse(headers={"Content-Type": "text/html"})
        await response.prepare(request)
        await response.write(b"<html><body><p>Humphrey Bogart")
        for _ in range(6):
            await asyncio.sleep(0.15)
            await response.write(b" as Rick Blaine")
        await response.write(b"</p></body></html>")
        return response

    async def latin1(request):
        return web.Response(body=LATIN1.encode("latin-1"), headers={"Content-Type": "text/html; charset=ISO-8859-1"})

    async def meta_latin1(request):
        html = '<html><head><meta charset="iso-8859-1"></head>' + LATIN1[6:]
        return web.Response(body=html.encode("latin-1"), headers={"Content-Type": "text/html"})

    async def big(request):
        filler = "Suo on suurempi kuin luulit. " * ((MAX_PAGE_BYTES + 1_000_000) // 29)
        return web.Response(text=f"<html><body><p>{BIG_START}</p><p>{filler}</p><p>{BIG_END}</p></body></html>",
                            content_type="text/html")

    async def pdf(request):
        return web.Response(body=b"%PDF-1.7 Humphrey Bogart as Rick Blaine", content_type="application/pdf")

    async def plain(request):
        return web.Response(text="Humphrey Bogart\n  as Rick Blaine", content_type="text/plain")

    async def moved(request):
        raise web.HTTPFound("/cast")

    async def missing(request):
        return web.Response(text=CAST_PAGE, content_type="text/html", status=404)

    @web.middleware
    async def record(request, handler):
        site.hits.append(request.path)
        return await handler(request)

    app = web.Application(middlewares=[record])
    app.router.add_get("/cast", page)
    app.router.add_get("/slow", slow)
    app.router.add_get("/slow-body", slow_body)
    app.router.add_get("/latin1", latin1)
    app.router.add_get("/meta-latin1", meta_latin1)
    app.router.add_get("/big", big)
    app.router.add_get("/paper.pdf", pdf)
    app.router.add_get("/plain.txt", plain)
    app.router.add_get("/moved", moved)
    app.router.add_get("/missing", missing)
    site = Site(await aiohttp_server(app))
    return site


@pytest.fixture
async def http():
    """The real download client, allowed to reach the local server."""
    async with download_client(allow_private=True) as client:
        yield client


async def test_an_excerpt_on_the_page_is_verified(site, http):
    result = await page_match("Directed by Michael Curtiz - a \"romantic drama\"", site("/cast"), 3, client=http)
    assert result.verified and result.reason is None and result.match == "normalised"
    assert result.status == 200 and result.content_type.startswith("text/html")
    assert result.bytes_read == len(CAST_PAGE.encode()) and not result.truncated and result.elapsed_s < 3


async def test_table_cells_dont_run_together(site, http):
    assert (await page_match(BOGART, site("/cast"), 3, client=http)).match == "normalised"
    assert (await page_match("Humphrey BogartRick Blaine", site("/cast"), 3, client=http)).match == "spaceless"


async def test_text_in_a_script_isnt_on_the_page(site, http):
    result = await page_match("Ronald Reagan as Rick Blaine", site("/cast"), 3, client=http)
    assert not result.verified and result.reason == "not-found" and result.match is None and result.status == 200


async def test_a_short_excerpt_is_never_looked_for(site, http):
    for excerpt in ("1942", "Ilsa Lund", "“Rick Blaine”", "Humphrey Bogart"):
        result = await page_match(excerpt, site("/cast"), 3, client=http)
        assert not result.verified and result.reason == "too-short"
    assert (await page_match(" “ ” … ", site("/cast"), 3, client=http)).reason == "no-excerpt"
    assert site.hits == []


async def test_a_slow_page_times_out(site, http):
    result = await page_match(BOGART, site("/slow"), 0.2, client=http)
    assert not result.verified and result.reason == "timeout" and result.elapsed_s < 0.9


async def test_the_timeout_covers_the_whole_download_not_each_read(site, http):
    result = await page_match("Humphrey Bogart as Rick Blaine", site("/slow-body"), 0.3, client=http)
    assert result.reason == "timeout" and result.status == 200 and result.elapsed_s < 0.9


async def test_a_page_that_isnt_html_is_not_searched(site, http):
    result = await page_match("Humphrey Bogart as Rick Blaine", site("/paper.pdf"), 3, client=http)
    assert result.reason == "not-html" and result.content_type == "application/pdf" and result.bytes_read == 0


async def test_a_plain_text_page_is_searched_as_it_is(site, http):
    result = await page_match("Humphrey Bogart as Rick Blaine", site("/plain.txt"), 3, client=http)
    assert result.verified


async def test_an_error_status_is_a_failed_download(site, http):
    result = await page_match(BOGART, site("/missing"), 3, client=http)
    assert result.reason == "download-failed" and result.status == 404 and result.error == "HTTP 404"


async def test_redirects_are_followed(site, http):
    result = await page_match("Ingrid Bergman Ilsa Lund", site("/moved"), 3, client=http)
    assert result.verified and result.final_url == site("/cast")
    assert site.hits == ["/moved", "/cast"]


async def test_the_charset_comes_from_the_header_or_a_meta_tag(site, http):
    excerpt = "Pietarsaaren väkiluku on noin 19 000"
    assert (await page_match(excerpt, site("/latin1"), 3, client=http)).verified
    assert (await page_match(excerpt, site("/meta-latin1"), 3, client=http)).verified


async def test_a_big_page_is_searched_up_to_the_cap(site, http):
    start = await page_match(BIG_START, site("/big"), 5, client=http)
    assert start.verified and start.truncated and start.bytes_read == MAX_PAGE_BYTES
    end = await page_match(BIG_END, site("/big"), 5, client=http)
    assert end.reason == "not-found" and end.truncated


async def test_a_page_under_a_smaller_cap(site, http):
    result = await page_match("Ingrid Bergman Ilsa Lund", site("/cast"), 3, client=http, max_bytes=200)
    assert result.reason == "not-found" and result.truncated and result.bytes_read == 200


async def test_a_refused_connection_is_a_failed_download(http):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    result = await page_match(BOGART, f"http://127.0.0.1:{port}/", 3, client=http)
    assert result.reason == "download-failed" and result.error.startswith("ConnectError") and result.status is None


async def test_nothing_is_downloaded_for_an_unreadable_url():
    def refuse(request):
        raise AssertionError(f"downloaded {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        for url in ("javascript:alert(1)", "ftp://example.org/", "https://"):
            result = await page_match(BOGART, url, 3, client=client)
            assert result.reason == "download-failed" and result.error == "unreadable URL"


async def test_whatever_goes_wrong_leaves_the_card_unverified():
    def broken(request):
        raise RuntimeError("something odd")

    async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as client:
        result = await page_match(BOGART, "https://example.org/", 3, client=client)
    assert result.reason == "download-failed" and result.error == "RuntimeError: something odd"


async def test_the_result_is_ready_for_the_recording(site, http):
    result = await page_match(BOGART, site("/cast"), 3, client=http)
    event = json.loads(json.dumps(result.event()))
    assert event["verified"] is True and event["match"] == "normalised" and event["status"] == 200
    assert set(event) == {"verified", "reason", "match", "status", "content_type", "final_url", "elapsed_s",
                          "bytes_read", "truncated", "error"}


# --- Private addresses -----------------------------------------------------------------

PUBLIC = "93.184.215.14"


@pytest.fixture
async def dns(monkeypatch):
    """Fake name lookups for `refuse_private`: a name maps to its addresses,
    an exception to raise, or is looked up for real."""
    loop = asyncio.get_running_loop()
    real, names = loop.getaddrinfo, {}

    async def getaddrinfo(host, port, *args, **kwargs):
        if host not in names:
            return await real(host, port, *args, **kwargs)
        if isinstance(names[host], Exception):
            raise names[host]
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0))
                for a in names[host]]

    monkeypatch.setattr(loop, "getaddrinfo", getaddrinfo)
    return names


async def test_the_download_client_refuses_private_addresses_unless_told_otherwise():
    async with download_client() as default, download_client(allow_private=True) as allowing:
        assert default.event_hooks["request"] == [refuse_private]
        assert allowing.event_hooks["request"] == []


async def test_the_default_client_refuses_this_machine(site):
    for url in (site("/cast"), site("/cast").replace("127.0.0.1", "localhost")):
        result = await page_match(BOGART, url, 3)
        assert not result.verified and result.reason == "download-failed"
        assert result.error.startswith("PrivateAddress") and result.status is None
    assert site.hits == []


@pytest.mark.parametrize("url", [
    "http://10.0.0.1/", "http://192.168.1.1/admin", "http://172.16.0.1/", "http://100.64.0.1/",
    "http://169.254.169.254/latest/meta-data/", "http://0.0.0.0/", "http://[::1]:8080/", "http://[fe80::1]/",
    "http://[fd00::1]/", "http://[::ffff:127.0.0.1]/",
])
async def test_the_default_client_refuses_private_ip_addresses(url):
    result = await page_match(BOGART, url, 3)
    assert result.reason == "download-failed" and result.error.startswith("PrivateAddress")


@pytest.mark.parametrize(("addresses", "refused"), [
    ([PUBLIC], False),
    ([PUBLIC, "2606:2800:21f:cb07:6820:80da:af6b:8b2c"], False),
    (["127.0.0.1"], True),
    ([PUBLIC, "10.1.2.3"], True),  # every address must be public
    (["fe80::1%eth0"], True),
    ([], True),
])
async def test_a_host_name_must_resolve_to_public_addresses_only(dns, addresses, refused):
    dns["source.example"] = addresses
    request = httpx.Request("GET", "https://source.example/page")
    if refused:
        with pytest.raises(PrivateAddress, match="source.example"):
            await refuse_private(request)
    else:
        assert await refuse_private(request) is None


async def test_a_public_ip_address_is_allowed_without_a_lookup(dns):
    assert await refuse_private(httpx.Request("GET", f"http://{PUBLIC}/")) is None


async def test_a_name_that_doesnt_resolve_is_a_failed_download(dns):
    dns["nowhere.example"] = socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    result = await page_match(BOGART, "https://nowhere.example/", 3)
    assert result.reason == "download-failed" and result.error.startswith("gaierror")


async def test_a_redirect_to_a_private_address_is_refused(dns):
    """Every hop is checked: a public page can't send the download inside."""
    dns["source.example"] = [PUBLIC]
    asked = []

    def handler(request):
        asked.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://10.0.0.5/secret"})

    hooks = {"request": [refuse_private]}  # as download_client() sets them
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True,
                                 event_hooks=hooks) as client:
        result = await page_match(BOGART, "https://source.example/page", 3, client=client)
    assert result.reason == "download-failed" and result.error == "PrivateAddress: 10.0.0.5 isn't a public address"
    assert asked == ["https://source.example/page"]


# --- The bands ----------------------------------------------------------------------


def card(finder="A", p=0.9, *, outcome=CLAIM_WRONG, verified=True, blocklisted=None, verdict=SUPPORTED):
    return Judged(finder, outcome, verified, blocklisted, verdict, p)


def no_card(finder, outcome):
    return Judged(finder, outcome)


def test_one_verified_supported_card_is_hedged():
    assert band_single(card(p=0.6), BANDS) == Band("hedged", "hedged:single-verified", "A")
    assert band_single(card("B", outcome=ANSWERED), BANDS) == Band("hedged", "hedged:single-verified", "B")


def test_one_card_alone_is_never_plain():
    assert band_single(card(p=1.0), BANDS).band == "hedged"
    assert band_pair(card(p=1.0), None, None, BANDS).band == "hedged"
    assert band_pair(None, card("B", p=1.0), Agreement(SAME_FACT, 1.0), BANDS) == \
        Band("hedged", "hedged:single-verified", "B")


def test_below_the_hedged_bar_nothing_is_shown():
    assert band_single(card(p=0.59), BANDS) == Band("none", "silent:low-support")


def test_with_no_probabilities_supported_meets_the_hedged_bar():
    assert band_single(card(p=None), BANDS) == Band("hedged", "hedged:single-verified", "A")
    assert band_single(card(p=None, verdict=NOT_SUPPORTED), BANDS) == Band("none", "silent:not-supported")


def test_the_verdicts_answer_names_its_category():
    assert band_single(card(p=0.7, verdict=NOT_SUPPORTED), BANDS) == Band("none", "silent:not-supported")
    assert band_single(card(p=0.7, verdict=DOESNT_ANSWER), BANDS) == Band("none", "silent:doesnt-answer")


def test_an_unverified_card_is_never_shown_alone():
    assert band_single(card(p=0.99, verified=False), BANDS) == Band("none", "silent:unverified")


def test_a_blocklisted_source_is_never_shown():
    assert band_single(card(blocklisted="reddit.com"), BANDS) == Band("none", "silent:blocklisted")
    assert band_single(card(blocklisted=UNREADABLE, verified=False), BANDS) == Band("none", "silent:blocklisted")


def test_a_card_with_no_verdict_is_not_shown():
    assert band_single(card(verdict=None, p=None), BANDS) == Band("none", "silent:no-verdict")


def test_outcomes_without_a_card_are_silent():
    assert band_single(no_card("A", CLAIM_RIGHT), BANDS) == Band("none", "silent:claim-right")
    assert band_single(no_card("B", NOT_FOUND), BANDS) == Band("none", "silent:not-found")


def test_the_thresholds_come_from_the_config():
    strict = dataclasses.replace(BANDS, hedged_supported=0.95)
    assert band_single(card(p=0.9), strict).reason == "silent:low-support"


def test_both_fact_finders_failing_is_no_band():
    with pytest.raises(ValueError, match="failed"):
        band_pair(None, None, None, BANDS)


def test_a_failed_fact_finder_leaves_the_other_card_alone():
    assert band_pair(card("A"), None, None, BANDS) == Band("hedged", "hedged:single-verified", "A")
    assert band_pair(None, card("B", verified=False), None, BANDS) == Band("none", "silent:unverified")
    assert band_pair(no_card("A", CLAIM_RIGHT), None, None, BANDS) == Band("none", "silent:claim-right")


def test_wrong_against_right_is_a_contradiction():
    assert band_pair(card("A", p=0.99), no_card("B", CLAIM_RIGHT), None, BANDS) == Band("none", "silent:contradiction")
    assert band_pair(no_card("A", CLAIM_RIGHT), card("B", p=0.99), None, BANDS) == Band("none", "silent:contradiction")


def test_a_card_against_not_found_is_judged_alone():
    assert band_pair(card("A"), no_card("B", NOT_FOUND), None, BANDS) == Band("hedged", "hedged:single-verified", "A")
    assert band_pair(no_card("A", NOT_FOUND), card("B", outcome=ANSWERED, p=0.5), None, BANDS) == \
        Band("none", "silent:low-support")


def test_no_card_from_either_is_silent():
    assert band_pair(no_card("A", NOT_FOUND), no_card("B", NOT_FOUND), None, BANDS).reason == "silent:not-found"
    assert band_pair(no_card("A", CLAIM_RIGHT), no_card("B", CLAIM_RIGHT), None, BANDS).reason == "silent:claim-right"
    assert band_pair(no_card("A", CLAIM_RIGHT), no_card("B", NOT_FOUND), None, BANDS).reason == "silent:claim-right"


def test_outcomes_that_cant_be_compared_are_silent():
    assert band_pair(card("A"), card("B", outcome=ANSWERED), Agreement(SAME_FACT, 0.9), BANDS) == \
        Band("none", "silent:mixed-outcomes")
    assert band_pair(card("A", outcome=ANSWERED), no_card("B", CLAIM_RIGHT), None, BANDS) == \
        Band("none", "silent:mixed-outcomes")


def test_two_cards_with_no_agreement_answer_are_silent():
    assert band_pair(card("A"), card("B"), None, BANDS) == Band("none", "silent:no-agreement")


def test_contradicting_cards_show_nothing():
    assert band_pair(card("A", p=0.99), card("B", p=0.99), Agreement(CONTRADICT, 0.1), BANDS) == \
        Band("none", "silent:contradiction")


def test_compatible_but_different_cards_are_each_judged_alone():
    compatible = Agreement(COMPATIBLE, 0.2)
    assert band_pair(card("A", p=0.7), card("B", p=0.95), compatible, BANDS) == Band("hedged", "hedged:compatible", "B")
    assert band_pair(card("A", p=0.7), card("B", verified=False), compatible, BANDS) == \
        Band("hedged", "hedged:compatible", "A")
    # Neither can be shown: the reason of the one that got further.
    assert band_pair(card("A", verified=False), card("B", p=0.5), compatible, BANDS) == \
        Band("none", "silent:low-support")


def test_an_agreeing_pair_over_the_plain_bar_is_plain():
    agreed = Agreement(SAME_FACT, 0.7)
    assert band_pair(card("A", p=0.85), card("B", p=0.5, verified=False), agreed, BANDS) == \
        Band("plain", "plain:agreed", "A")
    assert band_pair(card("A", p=0.5, verified=False), card("B", p=0.85), agreed, BANDS) == \
        Band("plain", "plain:agreed", "B")
    # The other card may have a blocklisted source; it isn't shown.
    assert band_pair(card("A", p=0.9), card("B", p=0.99, blocklisted="quora.com"), agreed, BANDS) == \
        Band("plain", "plain:agreed", "A")


@pytest.mark.parametrize(("p_same", "p_shown", "other"), [
    (0.69, 0.9, card("B", p=0.9)),
    (0.9, 0.84, card("B", p=0.6, verified=False)),
    (0.9, 0.9, card("B", p=0.49)),
    (0.9, 0.9, card("B", p=0.6, verdict=NOT_SUPPORTED)),
    (0.9, 0.9, card("B", p=None, verdict=None)),
])
def test_an_agreeing_pair_below_the_plain_bar_is_hedged(p_same, p_shown, other):
    assert band_pair(card("A", p=p_shown), other, Agreement(SAME_FACT, p_same), BANDS) == \
        Band("hedged", "hedged:agreed-below-plain", "A")


def test_the_verified_card_with_the_higher_support_is_shown():
    agreed = Agreement(SAME_FACT, 0.9)
    assert band_pair(card("A", p=0.9), card("B", p=0.95), agreed, BANDS).shown == "B"
    assert band_pair(card("A", p=0.9), card("B", p=0.95, verified=False), agreed, BANDS).shown == "A"
    assert band_pair(card("A", p=0.9), card("B", p=0.95, blocklisted="reddit.com"), agreed, BANDS).shown == "A"
    assert band_pair(card("A", p=0.9), card("B", p=0.9), agreed, BANDS).shown == "A"  # a tie: A


def test_an_agreeing_pair_needs_a_card_that_could_be_shown_alone():
    agreed = Agreement(SAME_FACT, 0.99)
    assert band_pair(card("A", verified=False), card("B", verified=False), agreed, BANDS) == \
        Band("none", "silent:unverified")
    assert band_pair(card("A", p=0.55), card("B", p=0.99, verified=False), agreed, BANDS) == \
        Band("none", "silent:low-support")


def test_with_no_probabilities_an_agreeing_pair_is_hedged_at_best():
    assert band_pair(card("A", p=None), card("B", p=None), Agreement(SAME_FACT), BANDS) == \
        Band("hedged", "hedged:no-probabilities", "A")
    assert band_pair(card("A", p=None, verified=False), card("B", p=None), Agreement(SAME_FACT), BANDS) == \
        Band("hedged", "hedged:no-probabilities", "B")


def test_typos_in_the_answers_are_caught():
    with pytest.raises(ValueError):
        Judged("A", "claim is false")
    with pytest.raises(ValueError):
        Judged("A", CLAIM_WRONG, True, None, "doesn’t answer the candidate", 0.9)
    with pytest.raises(ValueError):
        Judged("C", CLAIM_WRONG)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Agreement("same")


def results(p: float | None, **kwargs) -> list[Judged | None]:
    """Every kind of result one fact-finder can give, for the exhaustive test."""
    out: list[Judged | None] = [None, no_card("A", CLAIM_RIGHT), no_card("A", NOT_FOUND)]
    for outcome, verified, blocked, verdict in itertools.product(
            (CLAIM_WRONG, ANSWERED), (True, False), (None, "reddit.com"),
            (SUPPORTED, NOT_SUPPORTED, DOESNT_ANSWER, None)):
        out.append(Judged("A", outcome, verified, blocked, verdict, None if verdict is None else p))
    return out


def relabel(result: Judged | None, finder: str) -> Judged | None:
    return None if result is None else dataclasses.replace(result, finder=finder)


AGREEMENTS = [None, Agreement(CONTRADICT, 0.9), Agreement(COMPATIBLE, 0.9), Agreement(SAME_FACT, 0.6),
              Agreement(SAME_FACT, 0.9), Agreement(SAME_FACT)]


def test_every_band_keeps_the_rules():
    """Over every combination: a known reason code, a shown card that could
    be shown alone, plain only for an agreeing pair with probabilities, and
    the same band whichever fact-finder is A."""
    probabilities = (None, 0.55, 0.7, 0.9)
    for pa, pb in itertools.product(probabilities, probabilities):
        for a, b, agreement in itertools.product(results(pa), [relabel(r, "B") for r in results(pb)], AGREEMENTS):
            if a is None and b is None:
                continue
            band = band_pair(a, b, agreement, BANDS)
            assert band.reason in REASONS and band.reason.split(":")[0] == {"none": "silent"}.get(band.band, band.band)
            if band.band == "none":
                assert band.shown is None
                continue
            shown, other = (a, b) if band.shown == "A" else (b, a)
            assert shown.verified and not shown.blocklisted and shown.verdict == SUPPORTED
            assert shown.p_supported is None or shown.p_supported >= BANDS.hedged_supported
            if band.band == "plain":
                assert other is not None and agreement.answer == SAME_FACT
                assert agreement.p_same_fact >= 0.7 and shown.p_supported >= 0.85 and other.p_supported >= 0.5
            if {getattr(a, "outcome", None), getattr(b, "outcome", None)} == {CLAIM_WRONG, CLAIM_RIGHT}:
                pytest.fail("a contradiction was shown")
            swapped = band_pair(relabel(b, "A"), relabel(a, "B"), agreement, BANDS)
            assert (swapped.band, swapped.reason) == (band.band, band.reason)


# --- The words Carl adds ----------------------------------------------------------------


def test_the_words_on_a_hedged_card():
    assert card_words("claim", "hedged", "fi") == \
        {"label": "Väite", "tag": "Varauksin", "prefix": "Todennäköisesti:"}
    assert card_words("open question", "hedged", "en") == {"label": "Question", "tag": "Hedged", "prefix": "Probably:"}


def test_the_words_on_a_plain_card():
    assert card_words("open question", "plain", "fi") == {"label": "Kysymys", "tag": None, "prefix": ""}
    assert card_words("claim", "plain", "en") == {"label": "Claim", "tag": None, "prefix": ""}


def test_any_language_but_finnish_gets_english():
    assert card_words("claim", "hedged", "fi-FI")["label"] == "Väite"
    assert card_words("claim", "hedged", "FI")["label"] == "Väite"
    for language in ("sv", "", "fin"):
        assert card_words("claim", "hedged", language) == {"label": "Claim", "tag": "Hedged", "prefix": "Probably:"}


def test_no_words_for_no_card():
    with pytest.raises(ValueError):
        card_words("claim", "none", "fi")
    with pytest.raises(ValueError):
        card_words("none", "hedged", "fi")


def test_the_hedge_goes_before_the_fact_as_judged():
    fact = "Rickiä näytteli Humphrey Bogart, ei Ronald Reagan."
    assert hedged_fact(fact, card_words("claim", "hedged", "fi")["prefix"]) == \
        "Todennäköisesti: Rickiä näytteli Humphrey Bogart, ei Ronald Reagan."
    assert hedged_fact("Bogart played Rick.", "Probably:") == "Probably: Bogart played Rick."
    assert hedged_fact("Bogart played Rick.", "") == "Bogart played Rick."
