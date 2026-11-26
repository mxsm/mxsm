"""Read the total from the same Moe Counter namespace used by the profile README."""

import json
from urllib.parse import quote
from urllib.request import Request, urlopen


def fetch_views(owner, now):
    name = f":{owner}"
    url = "https://count.getloli.com/api/stats/series/" + quote(name, safe="")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": f"{owner}-profile-cards"})
    # The /record and image endpoints count a hit. Only the series endpoint is read-only.
    with urlopen(request, timeout=30) as response:
        data = json.load(response)
    count = data["total"]
    if data["name"] != name or type(count) is not int or count < 0:
        raise ValueError(f"Invalid profile view total for {name}")
    return {"owner": owner, "updated_at": now.isoformat(), "count": count}
