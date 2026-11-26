"""WSGI image endpoint for the GitHub profile's Foshan lion counter."""

import sys
from pathlib import Path
from xml.etree.ElementTree import ParseError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from render_views import render_views
from view_counter import original_counter_image, read_counter_image


def app(environ, start_response):
    headers = [("Cache-Control", "no-store, no-cache, max-age=0, must-revalidate"),
               ("Vercel-CDN-Cache-Control", "no-store")]
    method = environ["REQUEST_METHOD"]
    if method not in ("GET", "HEAD"):
        start_response("405 Method Not Allowed", headers + [("Allow", "GET, HEAD")])
        return []
    if method == "HEAD":
        start_response("200 OK", headers + [("Content-Type", "image/svg+xml")])
        return []
    try:
        count = read_counter_image(original_counter_image())
    except (OSError, ValueError, ParseError) as error:
        print(f"Profile counter unavailable: {error}", file=sys.stderr)
        start_response("503 Service Unavailable", headers + [("Retry-After", "15")])
        return []

    svg = render_views(count).encode("utf-8")
    start_response("200 OK", headers + [("Content-Type", "image/svg+xml; charset=utf-8"),
                                       ("Content-Length", str(len(svg)))])
    return [svg]
