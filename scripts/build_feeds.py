"""Build the public feed snapshot from config/feeds.json using the Python standard library."""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_FEEDS = 30
MAX_ITEMS = 150
PIN_LIFETIME = timedelta(hours=72)
CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
ACTIVE_EXPLOIT = re.compile(r"\b(?:actively exploited|active exploitation|zero[ -]day|remote code execution|rce)\b", re.IGNORECASE)
CRITICAL_EVENT = re.compile(r"\b(?:critical|severe|emergency|major)\b.*\b(?:security|vulnerability|flaw|outage|incident)\b|\b(?:security|vulnerability|flaw|outage|incident)\b.*\b(?:critical|severe|emergency|major)\b", re.IGNORECASE)
HIGH_EVENT = re.compile(r"\b(?:security update|security advisory|vulnerability|data breach|outage)\b", re.IGNORECASE)
RESOLVED_EVENT = re.compile(r"\b(?:resolved|restored|recovered|patched|fixed|patch released|fix released)\b", re.IGNORECASE)
VENDOR_ADVISORY = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/security/advisories/(GHSA-[A-Za-z0-9-]+)$")


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def public_url(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    try:
        parsed = urlparse(value)
        valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
    except ValueError:
        valid = False
    return value if valid else ""


def element_text(element):
    if element is None:
        return ""
    extractor = TextExtractor()
    extractor.feed(unescape("".join(element.itertext())))
    return " ".join(" ".join(extractor.parts).split())


def date_value(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def atom_link(entry, feed_url):
    for link in entry.findall(f"{ATOM}link"):
        candidate = urljoin(feed_url, link.get("href", ""))
        if link.get("rel", "alternate") == "alternate" and public_url(candidate):
            return candidate
    return ""


def parse_feed(data, url):
    root = ET.fromstring(data)
    channel = root.find("channel")
    if channel is not None:
        title = element_text(channel.find("title")) or urlparse(url).netloc
        entries = channel.findall("item")
        items = [
            {
                "title": element_text(entry.find("title")) or "Untitled entry",
                "url": public_url(urljoin(url, element_text(entry.find("link")))),
                "date": date_value(element_text(entry.find("pubDate"))),
                "summary": element_text(entry.find("description"))[:320],
            }
            for entry in entries
        ]
    elif root.tag == f"{ATOM}feed":
        title = element_text(root.find(f"{ATOM}title")) or urlparse(url).netloc
        entries = root.findall(f"{ATOM}entry")
        items = [
            {
                "title": element_text(entry.find(f"{ATOM}title")) or "Untitled entry",
                "url": atom_link(entry, url),
                "date": date_value(element_text(entry.find(f"{ATOM}published")) or element_text(entry.find(f"{ATOM}updated"))),
                "summary": element_text(entry.find(f"{ATOM}summary"))[:320],
            }
            for entry in entries
        ]
    else:
        raise ValueError("unsupported RSS or Atom document")
    return title, [item for item in items if item["url"]]


def github_json(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "RSSPriority/1.0"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = Request(f"https://api.github.com{path}", headers=headers)
    with urlopen(request, timeout=12) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("advisory response exceeds 2 MB")
    return json.loads(data)


def has_patched_versions(advisory):
    vulnerabilities = advisory.get("vulnerabilities") or []
    return bool(vulnerabilities) and all(
        vulnerability.get("patched_versions") or
        (vulnerability.get("first_patched_version") or {}).get("identifier")
        for vulnerability in vulnerabilities
    )


def advisory_status(cve):
    """Return severity and patch evidence from public and linked vendor advisories."""
    try:
        advisories = github_json(f"/advisories?cve_id={cve}&per_page=10")
        severity = None
        for advisory in advisories if isinstance(advisories, list) else []:
            if advisory.get("cve_id", "").upper() != cve:
                continue
            if advisory.get("severity") == "critical":
                severity = "critical"
            elif advisory.get("severity") == "high" and severity != "critical":
                severity = "high"
            if advisory.get("withdrawn_at") or has_patched_versions(advisory):
                return {"severity": severity, "cleared": True}
            vendor_checks = 0
            for reference in advisory.get("references", [])[:30]:
                parsed = urlparse(reference)
                match = VENDOR_ADVISORY.fullmatch(parsed.path) if parsed.netloc == "github.com" else None
                if not match:
                    continue
                if vendor_checks >= 3:
                    break
                vendor_checks += 1
                try:
                    vendor = github_json(f"/repos/{match[1]}/{match[2]}/security-advisories/{match[3]}")
                except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
                    continue
                if vendor.get("cve_id", "").upper() == cve and (vendor.get("withdrawn_at") or has_patched_versions(vendor)):
                    return {"severity": severity, "cleared": True}
        return {"severity": severity, "cleared": False}
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
        print(f"Warning: advisory lookup for {cve} unavailable", file=sys.stderr)
        return {"severity": None, "cleared": False}


def recent_date(value, now):
    if not value:
        return False
    try:
        published = datetime.fromisoformat(value)
    except ValueError:
        return False
    return timedelta(minutes=-10) <= now - published <= PIN_LIFETIME


def build_snapshot(feeds, items, now=None, lookup=advisory_status):
    now = now or datetime.now(timezone.utc)
    groups = {}
    for item in items:
        item["cves"] = sorted(set(match.upper() for match in CVE_PATTERN.findall(f"{item['title']} {item['summary']}")))
        for cve in item["cves"]:
            if recent_date(item["date"], now):
                groups.setdefault(cve, []).append(item)

    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = dict(zip(groups, executor.map(lookup, groups)))
    pins = []
    pinned_cves = set()
    for cve, reports in groups.items():
        status = statuses[cve]
        if status["cleared"]:
            continue
        reports.sort(key=lambda item: item["date"], reverse=True)
        latest = reports[0]
        text = " ".join(f"{item['title']} {item['summary']}" for item in reports)
        urgent = status["severity"] == "critical" or ACTIVE_EXPLOIT.search(text) or CRITICAL_EVENT.search(text) or re.search(r"\bPHP\b", text, re.IGNORECASE)
        if not urgent:
            continue
        pinned_cves.add(cve)
        pins.append({"id": cve, "cve": cve, "title": latest["title"], "url": latest["url"],
                     "feed": latest["feed"], "feedIds": sorted(set(item["feedId"] for item in reports)),
                     "date": latest["date"], "reports": len(reports), "reason": "Critical advisory" if status["severity"] == "critical" else "Urgent security report"})

    pinned_urls = set()
    resolved_urls = {item["url"] for item in items if RESOLVED_EVENT.search(item["title"])}
    for item in items:
        recent = recent_date(item["date"], now)
        text = f"{item['title']} {item['summary']}"
        if not item["cves"] and recent and item["url"] not in resolved_urls and (
            ACTIVE_EXPLOIT.search(text) or CRITICAL_EVENT.search(item["title"])
        ):
            pinned_urls.add(item["url"])
            pins.append({"id": item["url"], "cve": None, "title": item["title"], "url": item["url"],
                         "feed": item["feed"], "feedIds": [item["feedId"]], "date": item["date"],
                         "reports": 1, "reason": "Critical report"})
    for item in items:
        recent = recent_date(item["date"], now)
        text = f"{item['title']} {item['summary']}"
        if item["cves"] and all(statuses.get(cve, {}).get("cleared") for cve in item["cves"]):
            score = 0
        elif any(cve in pinned_cves for cve in item["cves"]) or item["url"] in pinned_urls:
            score = 100
        elif recent and (item["cves"] or HIGH_EVENT.search(text)):
            score = 50
        else:
            score = 0
        item["priorityScore"] = score

    pins.sort(key=lambda pin: pin["date"], reverse=True)
    items.sort(key=lambda item: (item["priorityScore"], item["date"] or ""), reverse=True)
    return {"updatedAt": now.isoformat(), "feeds": feeds, "pins": pins, "items": items[:MAX_ITEMS]}


def configured_urls():
    try:
        urls = json.loads((ROOT / "config" / "feeds.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read config/feeds.json: {error}") from error
    if not isinstance(urls, list) or len(urls) > MAX_FEEDS:
        raise SystemExit(f"config/feeds.json must contain at most {MAX_FEEDS} HTTP(S) feed URLs")
    urls = [public_url(url) for url in urls]
    if any(not url for url in urls):
        raise SystemExit("config/feeds.json must contain only public HTTP(S) feed URLs without credentials")
    return list(dict.fromkeys(urls))


def main():
    urls = configured_urls()

    feeds = []
    items = []
    for position, url in enumerate(urls, start=1):
        try:
            request = Request(url, headers={"User-Agent": "RSSPriority/1.0 (+https://github.com/BradleyBao/rss-priority)"})
            with urlopen(request, timeout=15) as response:
                data = response.read(5_000_001)
            if len(data) > 5_000_000:
                raise ValueError("feed exceeds 5 MB")
            title, entries = parse_feed(data, url)
            feed_id = str(len(feeds))
            feeds.append({"id": feed_id, "title": title, "count": len(entries)})
            items.extend({**entry, "feedId": feed_id, "feed": title} for entry in entries)
        except (OSError, ET.ParseError, ValueError) as error:
            print(f"Warning: feed #{position} failed ({type(error).__name__})", file=sys.stderr)

    if urls and not feeds:
        raise SystemExit("No feeds could be fetched; the existing published page was left intact")
    items.sort(key=lambda item: item["date"] or "", reverse=True)
    snapshot = build_snapshot(feeds, items[:MAX_ITEMS])
    (ROOT / "feeds.json").write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Built {len(snapshot['items'])} entries from {len(feeds)} feeds")


if __name__ == "__main__":
    main()
