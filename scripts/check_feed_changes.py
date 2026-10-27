"""Skip scheduled Pages deployments when the public feed snapshot is unchanged."""

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def feed_content(snapshot):
    return {key: snapshot[key] for key in ("feeds", "pins", "items")}


def should_deploy(snapshot, event_name, base_url):
    if event_name != "schedule":
        return True

    url = urljoin(base_url.rstrip("/") + "/", f"feeds.json?check={int(time.time())}")
    try:
        request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "RSSPriority/1.0"})
        with urlopen(request, timeout=12) as response:
            published = json.load(response)
        return feed_content(snapshot) != feed_content(published)
    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError):
        print("Published snapshot unavailable; deploying the new snapshot")
        return True


def main():
    snapshot = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    deploy = should_deploy(snapshot, os.environ.get("GITHUB_EVENT_NAME", ""),
                           os.environ.get("PAGES_BASE_URL", ""))
    result = "true" if deploy else "false"
    print("Deploying updated site" if deploy else "Feed content unchanged; skipping Pages deployment")
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"deploy={result}\n")


if __name__ == "__main__":
    main()
