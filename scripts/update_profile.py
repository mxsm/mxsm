"""Refresh a README card, or reproduce it offline from its checked-in JSON."""

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from github_stats import fetch_contributions, fetch_languages
from render_cards import RESOURCE, contribution_card, language_card
from render_views import render_views
from view_counter import fetch_views


def publish(output, card, snapshot, svg):
    ElementTree.fromstring(svg)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        f"{card}.svg": svg.encode("utf-8"),
        f"{card}.json": (json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    }
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        staged = Path(tmp)
        changed = []
        for name, content in files.items():
            target = output / name
            if target.exists():
                if target.read_bytes() == content:
                    continue
                shutil.copyfile(target, staged / (name + ".old"))
            (staged / name).write_bytes(content)
            changed.append(name)

        installed = []
        try:
            for name in changed:
                (staged / name).replace(output / name)
                installed.append(name)
        except OSError:
            for name in installed:
                backup = staged / (name + ".old")
                if backup.exists():
                    backup.replace(output / name)
                else:
                    (output / name).unlink()
            raise
    return bool(changed)


def monthly_snapshot(path, owner, now):
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(saved["updated_at"])
        rows = saved["languages"]
        if (saved["owner"], updated.year, updated.month) != (owner, now.year, now.month):
            return None
        if isinstance(rows, list) and all(
            isinstance(row["name"], str) and isinstance(row["color"], str)
            and isinstance(row["bytes"], int) and row["bytes"] > 0 for row in rows
        ):
            return saved
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        pass  # The next successful fetch repairs a missing or invalid snapshot.
    return None


def update(card, owner, now, output, *, render_only=False):
    path = output / f"{card}.json"
    snapshot = None
    if render_only:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    elif card == "languages":
        snapshot = monthly_snapshot(path, owner, now)

    if card == "languages":
        if snapshot is None:
            snapshot = fetch_languages(owner, now)
        svg = language_card(snapshot)
    elif card == "contributions":
        if snapshot is None:
            snapshot = fetch_contributions(owner, now)
        svg = contribution_card(snapshot)
    elif card == "profile-views":
        if snapshot is None:
            snapshot = fetch_views(owner, now)
            if path.exists():
                previous = json.loads(path.read_text(encoding="utf-8"))
                if previous["owner"] == owner and snapshot["count"] < previous["count"]:
                    raise ValueError("Profile view total decreased; keeping the last published count")
        svg = render_views(snapshot["count"])
    else:
        raise ValueError(f"Unknown profile card: {card}")
    changed = publish(output, card, snapshot, svg)
    print(f"{card}: {'updated' if changed else 'up to date'} (data from {snapshot['updated_at']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", choices=("languages", "contributions", "profile-views"))
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "mxsm"))
    parser.add_argument("--render-only", action="store_true", help="Render existing data without using GitHub.")
    args = parser.parse_args()
    update(
        args.card, args.owner, datetime.now(timezone.utc).replace(microsecond=0),
        RESOURCE / "generated", render_only=args.render_only,
    )
