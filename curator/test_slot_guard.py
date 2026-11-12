#!/usr/bin/env python3
# Offline tests. No credentials, API requests or repository changes.
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slot_guard as g

TZ = ZoneInfo('America/Chicago')


class GuardTests(unittest.TestCase):
    def at(self, day, hour, minute=0):
        return datetime(2026, 11, day, hour, minute, tzinfo=TZ)

    def test_before_morning_not_due(self):
        run, key, why = g.decide(self.at(12, 5, 50), {})
        self.assertFalse(run)
        self.assertEqual(key, '2026-11-11T17:43')

    def test_morning_due(self):
        run, key, _ = g.decide(self.at(12, 7, 13), {})
        self.assertTrue(run)
        self.assertEqual(key, '2026-11-12T06:43')

    def test_morning_after_missed_cron(self):
        run, key, _ = g.decide(self.at(12, 10, 17), {})
        self.assertTrue(run)
        self.assertEqual(key, '2026-11-12T06:43')

    def test_completed_slot_blocks_backups(self):
        state = {'2026-11-12T06:43': '2026-11-12T13:00:00+00:00'}
        self.assertFalse(g.decide(self.at(12, 7, 47), state)[0])
        self.assertFalse(g.decide(self.at(12, 10, 17), state)[0])

    def test_midday_is_distinct_slot(self):
        state = {'2026-11-12T06:43': '2026-11-12T13:00:00+00:00'}
        run, key, _ = g.decide(self.at(12, 12, 43), state)
        self.assertTrue(run)
        self.assertEqual(key, '2026-11-12T12:43')

    def test_evening_due(self):
        run, key, _ = g.decide(self.at(12, 18, 17), {})
        self.assertTrue(run)
        self.assertEqual(key, '2026-11-12T17:43')

    def test_stale_slot_skipped(self):
        self.assertFalse(g.decide(self.at(12, 23, 30), {})[0])

    def test_manual_can_catch_up_late(self):
        self.assertTrue(g.decide(self.at(12, 11, 45), {}, manual=True)[0])

    def test_force_allows_one_extra_manual(self):
        state = {'2026-11-12T06:43': '2026-11-12T13:00:00+00:00'}
        self.assertTrue(g.decide(self.at(12, 7, 30), state, manual=True, force=True)[0])

    def test_dst_uses_chicago_clock(self):
        spring = datetime(2027, 3, 14, 7, 0, tzinfo=TZ)
        fall = datetime(2027, 11, 7, 7, 0, tzinfo=TZ)
        self.assertEqual(g.slot_key(g.latest_slot(spring)), '2027-03-14T06:43')
        self.assertEqual(g.slot_key(g.latest_slot(fall)), '2027-11-07T06:43')
        self.assertNotEqual(g.latest_slot(spring).utcoffset(), g.latest_slot(fall).utcoffset())

    def test_mark_and_load(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'curator' / 'edition_state.json'
            now = self.at(12, 7, 13)
            g.mark_done('2026-11-12T06:43', now, p)
            self.assertIn('2026-11-12T06:43', g.load_state(p))
            with self.assertRaises(ValueError):
                g.mark_done('wrong', now, p)
            self.assertFalse(g.decide(now, g.load_state(p))[0])

    def test_no_state_file_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(g.load_state(Path(d) / 'missing.json'), {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
