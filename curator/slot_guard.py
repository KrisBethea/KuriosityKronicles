#!/usr/bin/env python3
# Guard scheduled Kuriosity Kronicles editions against missed triggers and duplicates.
# Python standard library only. Does not access Gemini or modify stories.
import argparse
import json
import os
import re
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / 'curator' / 'edition_state.json'
LOCAL_TZ = ZoneInfo('America/Chicago')
SLOT_TIMES = ((6, 43), (12, 43), (17, 43))
MAX_AGE = timedelta(hours=4)  # do not backfill yesterday's news at dawn
KEEP_DAYS = 21
KEY_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T(?:06|12|17):43$')


def latest_slot(now):
    """Most recent due edition, based on actual Chicago clock (DST aware)."""
    local_now = now.astimezone(LOCAL_TZ)
    for hour, minute in reversed(SLOT_TIMES):
        candidate = datetime.combine(local_now.date(), time(hour, minute), LOCAL_TZ)
        if candidate <= local_now:
            return candidate
    return datetime.combine(local_now.date() - timedelta(days=1), time(*SLOT_TIMES[-1]), LOCAL_TZ)


def slot_key(slot):
    return slot.strftime('%Y-%m-%dT%H:%M')


def load_state(path=STATE_PATH):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
        raise ValueError('Unexpected edition_state.json format; refusing to risk duplicates')
    return data


def decide(now, state, *, manual=False, force=False):
    """Return (run?, slot key, why). Force is an explicit manual override."""
    due = latest_slot(now)
    key = slot_key(due)
    if key in state and not force:
        return False, key, 'Already completed; no Gemini call needed'
    if now.astimezone(timezone.utc) - due.astimezone(timezone.utc) > MAX_AGE and not (manual or force):
        return False, key, 'Edition window expired; next scheduled slot will take over'
    return True, key, 'Manual override' if force else 'Edition needs curation'


def mark_done(key, now, path=STATE_PATH):
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError('Invalid edition key')
    state = load_state(path)
    cutoff = (now.astimezone(LOCAL_TZ).date() - timedelta(days=KEEP_DAYS)).isoformat()
    state = {k: v for k, v in state.items() if KEY_PATTERN.fullmatch(k) and k[:10] >= cutoff}
    state[key] = now.astimezone(timezone.utc).isoformat(timespec='seconds')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(state.items())), indent=2) + '\n', encoding='utf-8')
    return state


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='action', required=True)
    check = sub.add_parser('check', help='Determine if this edition needs a Gemini call')
    check.add_argument('--manual', action='store_true', help='Allow an overdue manual run')
    check.add_argument('--force', action='store_true', help='Explicitly permit a second run in the same slot')
    mark = sub.add_parser('mark', help='Record successful curation after the checker and builder pass')
    mark.add_argument('--slot', required=True)
    args = ap.parse_args()
    now = datetime.now(LOCAL_TZ)
    if args.action == 'check':
        run, key, why = decide(now, load_state(), manual=args.manual, force=args.force)
        print(f'Chicago: {now.isoformat(timespec="seconds")} | edition: {key} | {why}')
        outputs = os.environ.get('GITHUB_OUTPUT')
        if outputs:
            with open(outputs, 'a', encoding='utf-8') as f:
                f.write(f'should_run={str(run).lower()}\nslot={key}\n')
    else:
        mark_done(args.slot, now)
        print(f'Edition {args.slot} marked complete; later backups will skip Gemini.')


if __name__ == '__main__':
    main()
