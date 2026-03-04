# Notes issues

## 1. `get_daily_notes_range` doesn't filter empty notes

`database/records.py:247` has no `WHERE content != ''` clause, unlike `get_all_daily_notes` on line 265. `get_dates_with_notes` (feeds calendar indicators) compensates by filtering post-decryption in Python, but the inconsistency between the two query methods is a footgun.

