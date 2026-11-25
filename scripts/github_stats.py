"""Public repository statistics and the owner's GitHub contribution calendar."""

import json
import subprocess
from datetime import date, timedelta


REPOSITORIES = """
query($owner: String!, $after: String, $withLanguages: Boolean!, $forkFilter: Boolean) {
  user(login: $owner) {
    repositories(first: 50, after: $after, ownerAffiliations: [OWNER],
                 privacy: PUBLIC, isFork: $forkFilter, orderBy: {field: NAME, direction: ASC}) {
      nodes {
        name stargazerCount forkCount
        languages(first: 100) @include(if: $withLanguages) {
          edges { size node { name color } }
          pageInfo { hasNextPage endCursor }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

MORE_LANGUAGES = """
query($owner: String!, $repo: String!, $after: String!) {
  repository(owner: $owner, name: $repo) {
    languages(first: 100, after: $after) {
      edges { size node { name color } }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

CONTRIBUTIONS = """
query($owner: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $owner) {
    createdAt
    contributionsCollection(from: $from, to: $to) {
      commits: totalCommitContributions
      issues: totalIssueContributions
      prs: totalPullRequestContributions
      reviews: totalPullRequestReviewContributions
      repos: totalRepositoryContributions
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

HIDDEN_LANGUAGES = {"html", "javascript", "css", "freemarker"}


def graphql(query, **variables):
    response = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps({"query": query, "variables": variables}),
        capture_output=True, encoding="utf-8", timeout=90,
    )
    if response.returncode:
        raise RuntimeError(response.stderr.strip() or "GitHub API request failed")
    payload = json.loads(response.stdout)
    if payload.get("errors"):
        raise RuntimeError("; ".join(error["message"] for error in payload["errors"]))
    return payload["data"]


def repositories(owner, *, with_languages):
    after = None
    while True:
        # The language mix excludes forks; the profile's star and fork totals include all owned repos.
        user = graphql(
            REPOSITORIES, owner=owner, after=after, withLanguages=with_languages,
            forkFilter=False if with_languages else None,
        )["user"]
        if user is None:
            raise ValueError(f"GitHub user {owner!r} was not found")
        page = user["repositories"]
        yield from page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return
        after = page["pageInfo"]["endCursor"]


def language_edges(owner, repo):
    page = repo["languages"]
    while True:
        yield from page["edges"]
        if not page["pageInfo"]["hasNextPage"]:
            return
        page = graphql(
            MORE_LANGUAGES, owner=owner, repo=repo["name"], after=page["pageInfo"]["endCursor"],
        )["repository"]["languages"]


def fetch_languages(owner, now):
    sizes = {}
    colors = {}
    for repo in repositories(owner, with_languages=True):
        for edge in language_edges(owner, repo):
            language = edge["node"]
            name = language["name"]
            if name.casefold() not in HIDDEN_LANGUAGES and edge["size"] > 0:
                sizes[name] = sizes.get(name, 0) + edge["size"]
                colors[name] = language["color"] or "#9eabbc"
    ranked = sorted(sizes, key=lambda name: (-sizes[name], name.casefold()))[:10]
    return {
        "owner": owner, "updated_at": now.isoformat(),
        "languages": [{"name": name, "bytes": sizes[name], "color": colors[name]} for name in ranked],
    }


def calendar_days(weeks, start, end, account_created):
    # GitHub weeks may contain padding dates beyond the requested interval.
    calendar = {
        d["date"]: d["contributionCount"]
        for week in weeks for d in week["contributionDays"]
    }
    days = {}
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        count = calendar.get(key, 0 if day < account_created else None)
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"Incomplete contribution calendar for {key}")
        days[key] = count
    return days


def fetch_contributions(owner, now):
    end = now.date()
    start = end - timedelta(days=364)
    user = graphql(
        CONTRIBUTIONS, owner=owner, **{"from": f"{start}T00:00:00Z", "to": now.isoformat()},
    )["user"]
    if user is None:
        raise ValueError(f"GitHub user {owner!r} was not found")
    collection = user["contributionsCollection"]
    days = calendar_days(
        collection["contributionCalendar"]["weeks"], start, end, date.fromisoformat(user["createdAt"][:10]),
    )
    totals = {key: collection[key] for key in ("commits", "issues", "prs", "reviews", "repos")}
    totals.update(stars=0, forks=0)
    for repo in repositories(owner, with_languages=False):
        totals["stars"] += repo["stargazerCount"]
        totals["forks"] += repo["forkCount"]
    return {"owner": owner, "updated_at": now.isoformat(), "days": days, "totals": totals}
