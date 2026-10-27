import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import check_feed_changes
from scripts.check_feed_changes import should_deploy


class ChangeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"updatedAt": "2026-10-27T12:00:00Z", "feeds": [], "pins": [], "items": []}

    def test_scheduled_run_skips_when_only_build_time_changes(self):
        published = {**self.snapshot, "updatedAt": "2026-10-27T11:45:00Z"}
        with patch("scripts.check_feed_changes.urlopen", return_value=io.BytesIO(json.dumps(published).encode())) as fetch:
            self.assertFalse(should_deploy(self.snapshot, "schedule", "https://example.com/rss-priority"))
        self.assertEqual(fetch.call_args.args[0].full_url.split("?")[0],
                         "https://example.com/rss-priority/feeds.json")

    def test_scheduled_run_deploys_changed_content(self):
        published = {**self.snapshot, "pins": [{"id": "old"}]}
        with patch("scripts.check_feed_changes.urlopen", return_value=io.BytesIO(json.dumps(published).encode())):
            self.assertTrue(should_deploy(self.snapshot, "schedule", "https://example.com"))

    def test_scheduled_run_deploys_if_published_snapshot_is_missing(self):
        error = HTTPError("https://example.com/feeds.json", 404, "Not Found", {}, None)
        with patch("scripts.check_feed_changes.urlopen", side_effect=error):
            self.assertTrue(should_deploy(self.snapshot, "schedule", "https://example.com"))

    def test_push_deploys_without_fetching_published_snapshot(self):
        with patch("scripts.check_feed_changes.urlopen") as fetch:
            self.assertTrue(should_deploy(self.snapshot, "push", "https://example.com"))
        fetch.assert_not_called()

    def test_main_writes_skip_decision_for_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "feeds.json").write_text(json.dumps(self.snapshot), encoding="utf-8")
            output = root / "github-output"
            published = {**self.snapshot, "updatedAt": "2026-10-27T11:45:00Z"}
            with patch.object(check_feed_changes, "ROOT", root), \
                 patch.dict(check_feed_changes.os.environ, {
                     "GITHUB_EVENT_NAME": "schedule", "PAGES_BASE_URL": "https://example.com/rss-priority",
                     "GITHUB_OUTPUT": str(output)
                 }), \
                 patch.object(check_feed_changes, "urlopen", return_value=io.BytesIO(json.dumps(published).encode())):
                check_feed_changes.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "deploy=false\n")


if __name__ == "__main__":
    unittest.main()
