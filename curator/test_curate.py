#!/usr/bin/env python3
"""Offline unit tests for candidate selection, strict mapping and failure handling."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curate


class CuratorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 13, 30, tzinfo=ZoneInfo("America/Chicago"))
        self.first = {
            "title": "Aurora researchers measure a large substorm", "source": "Journal of Sky",
            "link": "https://example.org/storm-1", "image": "https://example.org/photo.jpg",
            "category": "Space Weather and Aurora", "summary": "Researchers compared ground magnetometers and satellite readings to track the onset and spread of an auroral substorm.",
            "published": "2026-11-10T09:00:00-06:00",
        }
        self.second = {
            "title": "New code analysis tool for .NET", "source": "Dev Journal",
            "link": "https://example.org/dotnet", "category": "DotNet and Development",
            "summary": "New open-source diagnostics help developers identify practical performance regressions in existing C# and ASP.NET applications.",
            "published": "2026-11-10T08:00:00-06:00",
        }
        self.valid = {
            "picks": [{
                "index": 0, "title": "Researchers track the stages of an auroral substorm",
                "category": "Space Weather and Aurora",
                "dept": "from the magnetometers-mean-business dept.",
                "reasoning": "This connects the aurora to the measurements that reveal its onset. It is a useful reminder that a glowing sky can be quantified.",
                "summary": "Researchers compared satellite and ground measurements during a substorm. The work examined how the auroral disturbance began and expanded.",
            }]
        }

    def test_model_only_gets_candidate_indices_not_links(self):
        payload = curate.model_payload([self.first], [])
        request = json.loads(payload["contents"][0]["parts"][0]["text"])
        self.assertEqual(request["candidates"][0]["index"], 0)
        self.assertNotIn("link", request["candidates"][0])
        self.assertNotIn("image", request["candidates"][0])

    def test_copies_real_link_source_and_image(self):
        items = curate.validate_and_materialize(self.valid, [self.first], [], self.now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], self.first["link"])
        self.assertEqual(items[0]["id"], self.first["link"])
        self.assertEqual(items[0]["source"], self.first["source"])
        self.assertEqual(items[0]["image"], self.first["image"])
        self.assertEqual(items[0]["added"], "2026-11-10T13:30:00-06:00")

    def test_reject_wrong_category(self):
        bad = json.loads(json.dumps(self.valid)); bad["picks"][0]["category"] = "Nonsense"
        with self.assertRaises(ValueError):
            curate.validate_and_materialize(bad, [self.first], [], self.now)

    def test_reject_repeat(self):
        prior = [{"link": self.first["link"], "title": "Old version"}]
        with self.assertRaises(ValueError):
            curate.validate_and_materialize(self.valid, [self.first], prior, self.now)

    def test_reject_duplicate_indexes(self):
        bad = json.loads(json.dumps(self.valid)); bad["picks"].append(dict(bad["picks"][0]))
        with self.assertRaises(ValueError):
            curate.validate_and_materialize(bad, [self.first], [], self.now)

    def test_reject_made_up_index(self):
        bad = json.loads(json.dumps(self.valid)); bad["picks"][0]["index"] = 100
        with self.assertRaises(ValueError):
            curate.validate_and_materialize(bad, [self.first], [], self.now)

    def test_reject_urls_in_editorial_text(self):
        bad = json.loads(json.dumps(self.valid)); bad["picks"][0]["summary"] += " See https://evil.example/test"
        with self.assertRaises(ValueError):
            curate.validate_and_materialize(bad, [self.first], [], self.now)

    def test_no_model_swap_to_paid_variant(self):
        with self.assertRaises(ValueError):
            curate.request_gemini({}, "fake", model="gemini-2.5-pro")

    def test_reject_oversized_batch(self):
        bad = json.loads(json.dumps(self.valid)); bad["picks"] *= 9
        with self.assertRaises(ValueError):
            curate.validate_and_materialize(bad, [self.first], [], self.now)

    def test_skip_seen_candidates(self):
        chosen = curate.candidate_selection([self.first, self.second], {curate.norm(self.first["link"])})
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["link"], self.second["link"])

    def test_submitted_preserves_attribution(self):
        submitted = {**self.first, "tier": "submitted", "submitted_by": "Kris"}
        items = curate.validate_and_materialize(self.valid, [submitted], [], self.now)
        self.assertEqual(items[0]["submitted_by"], "Kris")

    def test_http_failure_does_not_log_key(self):
        from urllib.error import HTTPError
        with patch.object(curate, "urlopen", side_effect=HTTPError("test", 429, "limit", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "HTTP 429") as cm:
                curate.request_gemini({}, "private-key")
        self.assertNotIn("private-key", str(cm.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
