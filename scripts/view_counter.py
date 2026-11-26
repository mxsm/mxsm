"""Read the total from the same Moe Counter namespace used by the profile README."""

import json
import re
from functools import lru_cache
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class CounterImage(HTMLParser):
    def __init__(self, owner):
        super().__init__()
        self.canonical = f"https://count.getloli.com/get/@:{owner}"
        self.url = None

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            image = dict(attrs)
            if image.get("data-canonical-src", "").partition("?")[0] == self.canonical:
                self.url = image.get("src")


def counter_image_url(owner, page):
    profile = CounterImage(owner)
    with urlopen(page, timeout=10) as response:
        profile.feed(response.read().decode("utf-8"))
    if not profile.url or not profile.url.startswith("https://camo.githubusercontent.com/"):
        raise ValueError("Could not locate the original counter on the GitHub profile")
    return profile.url


def read_counter_image(url):
    with urlopen(url, timeout=10) as response:
        image = ElementTree.parse(response)
    href = "{http://www.w3.org/1999/xlink}href"
    digits = [use.get(href, "") for use in image.findall(".//{http://www.w3.org/2000/svg}use")]
    if not digits or any(not re.fullmatch(r"#[0-9]", digit) for digit in digits):
        raise ValueError("The displayed counter did not contain a valid digit sequence")
    return int("".join(digit[1] for digit in digits))


def displayed_total(owner):
    page = f"https://github.com/{quote(owner, safe='')}"
    return read_counter_image(counter_image_url(owner, page))


@lru_cache(maxsize=1)
def original_counter_image():
    # Resolve the counter from the published README before the live card replaced it.
    # Only its URL is cached. The image itself records a new hit on each fetch.
    page = Request(
        "https://api.github.com/repos/mxsm/mxsm/readme?ref=b8248ab3a3956e8445927428046c9f5e1da1eec9",
        headers={"Accept": "application/vnd.github.html+json", "User-Agent": "mxsm-profile-views"},
    )
    return counter_image_url("mxsm", page)


def series_total(owner):
    name = f":{owner}"
    url = "https://count.getloli.com/api/stats/series/" + quote(name, safe="")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": f"{owner}-profile-cards"})
    # The /record and image endpoints count a hit. Only the series endpoint is read-only.
    with urlopen(request, timeout=30) as response:
        data = json.load(response)
    count = data["total"]
    if data["name"] != name or type(count) is not int or count < 0:
        raise ValueError(f"Invalid profile view total for {name}")
    return count


def fetch_views(owner, now):
    try:
        count = series_total(owner)
        source = "counter-api"
    except (URLError, TimeoutError) as error:
        print(f"Counter API unavailable ({error}). Reading the counter image from the GitHub profile.")
        count = displayed_total(owner)
        source = "profile-counter-image"
    return {"owner": owner, "updated_at": now.isoformat(), "count": count, "source": source}
