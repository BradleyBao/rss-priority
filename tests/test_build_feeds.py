import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import build_feeds
from scripts.build_feeds import parse_feed, public_url


class FeedParsingTests(unittest.TestCase):
    def test_rss_text_dates_and_relative_links(self):
        xml = b'''<rss version="2.0"><channel><title>Example</title><item>
          <title>First story</title><link>/stories/one</link>
          <pubDate>Tue, 27 Oct 2026 09:00:00 GMT</pubDate>
          <description>&lt;p&gt;A &lt;strong&gt;short&lt;/strong&gt; summary.&lt;/p&gt;</description>
        </item></channel></rss>'''
        title, entries = parse_feed(xml, "https://example.com/feed.xml")
        self.assertEqual(title, "Example")
        self.assertEqual(entries[0]["url"], "https://example.com/stories/one")
        self.assertEqual(entries[0]["summary"], "A short summary.")
        self.assertEqual(entries[0]["date"], "2026-10-27T09:00:00+00:00")

    def test_atom_alternate_link_and_summary(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Notes</title><entry>
          <title>New entry</title><link rel="self" href="/feed/entry"/>
          <link rel="alternate" href="/posts/entry"/>
          <updated>2026-10-27T12:00:00Z</updated><summary>Read this</summary>
        </entry></feed>'''
        title, entries = parse_feed(xml, "https://example.org/atom.xml")
        self.assertEqual(title, "Notes")
        self.assertEqual(entries[0]["url"], "https://example.org/posts/entry")
        self.assertEqual(entries[0]["summary"], "Read this")

    def test_non_web_and_credentialed_urls_are_rejected(self):
        self.assertFalse(public_url("javascript:alert(1)"))
        self.assertFalse(public_url("https://user:pass@example.com/feed"))
        self.assertFalse(public_url("https://[invalid/feed"))

    def test_build_snapshot_omits_configured_feed_url(self):
        xml = b'''<rss><channel><title>Example</title><item>
          <title>Story</title><link>https://example.com/story</link>
        </item></channel></rss>'''
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config" / "feeds.json"
            config.parent.mkdir()
            config.write_text('["https://example.com/feed.xml"]')
            with patch.object(build_feeds, "ROOT", Path(directory)), \
                 patch.object(build_feeds, "urlopen", return_value=io.BytesIO(xml)), \
                 patch.dict(build_feeds.os.environ, {"RSS_FEEDS": "not used"}):
                build_feeds.main()
            snapshot = json.loads((Path(directory) / "feeds.json").read_text())
        self.assertEqual(snapshot["items"][0]["url"], "https://example.com/story")
        self.assertNotIn("url", snapshot["feeds"][0])

    def test_empty_config_builds_empty_board(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config" / "feeds.json"
            config.parent.mkdir()
            config.write_text("[]")
            with patch.object(build_feeds, "ROOT", Path(directory)), \
                 patch.object(build_feeds, "urlopen") as fetch:
                build_feeds.main()
            snapshot = json.loads((Path(directory) / "feeds.json").read_text())
        fetch.assert_not_called()
        self.assertEqual(snapshot["feeds"], [])
        self.assertEqual(snapshot["items"], [])
        self.assertEqual(snapshot["pins"], [])

    def test_config_rejects_tokenized_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config" / "feeds.json"
            config.parent.mkdir()
            config.write_text('["https://user:token@example.com/feed"]')
            with patch.object(build_feeds, "ROOT", Path(directory)):
                with self.assertRaisesRegex(SystemExit, "without credentials"):
                    build_feeds.configured_urls()


class PriorityTests(unittest.TestCase):
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)

    def item(self, title, url, hours_ago=1, feed_id="0"):
        return {"title": title, "url": url, "summary": "", "feed": "Security Desk",
                "feedId": feed_id, "date": (self.now - timedelta(hours=hours_ago)).isoformat()}

    def test_multiple_cves_pin_and_reports_group(self):
        items = [
            self.item("Critical PHP CVE-2099-12345", "https://example.com/a"),
            self.item("Update on CVE-2099-12345", "https://example.com/b", feed_id="1"),
            self.item("Actively exploited CVE-2099-67890", "https://example.com/c"),
            self.item("Regular news", "https://example.com/d", hours_ago=0),
        ]
        snapshot = build_feeds.build_snapshot([], items, self.now, lambda cve: {"severity": "critical", "cleared": False})
        self.assertEqual({pin["cve"] for pin in snapshot["pins"]}, {"CVE-2099-12345", "CVE-2099-67890"})
        grouped = next(pin for pin in snapshot["pins"] if pin["cve"] == "CVE-2099-12345")
        self.assertEqual(grouped["reports"], 2)
        self.assertEqual(grouped["feedIds"], ["0", "1"])
        self.assertEqual(snapshot["items"][0]["priorityScore"], 100)

    def test_two_cves_in_one_incident_make_one_pin(self):
        item = self.item("PHP2Shell flaws now exploited in the wild", "https://example.com/php2shell")
        item["summary"] = "CVE-2099-12345 and CVE-2099-67890 are under active exploitation."
        snapshot = build_feeds.build_snapshot([], [item], self.now, lambda cve: {"severity": None, "cleared": False})
        self.assertEqual(len(snapshot["pins"]), 1)
        self.assertEqual(snapshot["pins"][0]["cves"], ["CVE-2099-12345", "CVE-2099-67890"])
        self.assertEqual(snapshot["pins"][0]["reports"], 1)

    def test_active_followup_joins_cve_incident_without_editorial_story(self):
        initial = self.item("PHP2Shell flaws now exploited in the wild", "https://example.com/initial", hours_ago=2)
        initial["summary"] = "CVE-2099-12345 and CVE-2099-67890"
        followup = self.item("CISA confirms PHP2Shell vulnerabilities now exploited in attacks", "https://example.com/followup")
        commentary = self.item("Wiz: No successful PHP2Shell exploits seen so far", "https://example.com/commentary", hours_ago=0)
        snapshot = build_feeds.build_snapshot([], [initial, followup, commentary], self.now,
                                              lambda cve: {"severity": None, "cleared": False})
        self.assertEqual(len(snapshot["pins"]), 1)
        self.assertEqual(snapshot["pins"][0]["title"], followup["title"])
        self.assertEqual(snapshot["pins"][0]["reports"], 2)
        self.assertEqual(set(snapshot["pins"][0]["urls"]), {initial["url"], followup["url"]})

    def test_patch_removes_pin_and_recent_report_stays_in_news(self):
        item = self.item("Critical PHP CVE-2099-12345", "https://example.com/a")
        snapshot = build_feeds.build_snapshot([], [item], self.now, lambda cve: {"severity": "critical", "cleared": True})
        self.assertEqual(snapshot["pins"], [])
        self.assertEqual(snapshot["items"][0]["priorityScore"], 0)

    def test_pin_expires_after_72_hours(self):
        item = self.item("Critical PHP CVE-2099-12345", "https://example.com/a", hours_ago=73)
        snapshot = build_feeds.build_snapshot([], [item], self.now, lambda cve: {"severity": "critical", "cleared": False})
        self.assertEqual(snapshot["pins"], [])
        self.assertEqual(snapshot["items"][0]["priorityScore"], 0)

    def test_resolved_non_cve_report_clears_matching_url(self):
        url = "https://example.com/incident/123"
        items = [self.item("Major outage affects downloads", url), self.item("Outage resolved", url, hours_ago=0)]
        snapshot = build_feeds.build_snapshot([], items, self.now, lambda cve: None)
        self.assertEqual(snapshot["pins"], [])

    def test_recent_critical_non_cve_report_is_pinned(self):
        item = self.item("Major outage affects downloads", "https://example.com/incident/123")
        snapshot = build_feeds.build_snapshot([], [item], self.now, lambda cve: None)
        self.assertEqual(len(snapshot["pins"]), 1)
        self.assertIsNone(snapshot["pins"][0]["cve"])
        self.assertEqual(snapshot["items"][0]["priorityScore"], 100)

    def test_patch_news_and_summary_keywords_do_not_create_pins(self):
        patch_news = self.item("HPE Patches Dozens of Critical Flaws in Networking Products", "https://example.com/hpe")
        patch_news["summary"] = "Eight max-severity defects could lead to remote code execution."
        zero_day_patch = self.item("Apple backports zero-day patches to older phones", "https://example.com/apple")
        general = self.item("Critical HTTP2Shell vulnerability triggers emergency patches", "https://example.com/http")
        snapshot = build_feeds.build_snapshot([], [patch_news, zero_day_patch, general], self.now,
                                              lambda cve: None)
        self.assertEqual(snapshot["pins"], [])

    def test_patch_announcement_does_not_pin_cve_with_incomplete_advisory(self):
        item = self.item("Critical CVE-2099-12345 patched in emergency release", "https://example.com/patch")
        snapshot = build_feeds.build_snapshot([], [item], self.now,
                                              lambda cve: {"severity": "critical", "cleared": False})
        self.assertEqual(snapshot["pins"], [])

    def test_vendor_advisory_patched_versions_clear_cve(self):
        public = [{"cve_id": "CVE-2024-4577", "severity": "critical", "vulnerabilities": [],
                   "references": ["https://github.com/php/php-src/security/advisories/GHSA-3qgc-jrrr-25jv"]}]
        vendor = {"cve_id": "CVE-2024-4577", "vulnerabilities": [
            {"patched_versions": "8.1.29"}, {"patched_versions": "8.2.20"}, {"patched_versions": "8.3.8"}]}
        with patch.object(build_feeds, "github_json", side_effect=[public, vendor]):
            status = build_feeds.advisory_status("CVE-2024-4577")
        self.assertEqual(status, {"severity": "critical", "cleared": True})


if __name__ == "__main__":
    unittest.main()
