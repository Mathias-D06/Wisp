"""Web tools (skill group "web"): searches and URLs in the default browser.

``webbrowser.open`` uses the system default browser (docs.python.org/3/library/webbrowser.html;
on Windows it calls os.startfile).
"""

from __future__ import annotations

import re
import webbrowser
from urllib.parse import quote_plus, urlparse

from wisp.tools.base import Tool, ToolContext, ToolError, obj, string

SITES = {
    "google": "https://www.google.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "amazon": "https://{domain}/s?k={q}",
}


def search_url(site: str, query: str, amazon_domain: str = "www.amazon.com") -> str:
    if site not in SITES:
        raise ToolError(f"Unknown site {site}.")
    return SITES[site].format(q=quote_plus(query), domain=amazon_domain)


def web_search(ctx: ToolContext, args: dict) -> dict:
    site = args.get("site", "google")
    domain = ctx.services.settings.peek().general.amazon_domain
    url = search_url(site, args["query"], domain)
    webbrowser.open(url)
    return {"opened": url}


_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:(?!\d)")


def open_url(ctx: ToolContext, args: dict) -> dict:
    url = args["url"].strip()
    if not _SCHEME.match(url):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ToolError("Only http and https web addresses can be opened.")
    webbrowser.open(url)
    return {"opened": url}


def tools() -> list[Tool]:
    return [
        Tool("web_search", "Search Google, YouTube or Amazon in the default browser.",
             obj({"query": string("What to search for"),
                  "site": string("Where to search", list(SITES))}, ["query"]),
             web_search, "web", summary=lambda a: f"search {a.get('site', 'google')} for "
             f"'{a.get('query')}'"),
        Tool("open_url", "Open a web address in the default browser.",
             obj({"url": string("http(s) address")}, ["url"]), open_url, "web",
             escalate_when_tainted=True, summary=lambda a: f"open {a.get('url')}"),
    ]
