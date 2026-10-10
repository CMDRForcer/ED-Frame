"""Observation-age policy shared by Powerplay retrieval and route scoring.

Age belongs to each observed field, never to a download or cache write.
Historical explicit control can suggest a route, but cannot verify it.
"""
POWERPLAY_CURRENT_HOURS = 48
POWERPLAY_LAST_KNOWN_HOURS = 14 * 24
# The existing public server supports at most seven days per regional query.
POWERPLAY_SERVER_HISTORY_HOURS = 7 * 24


def powerplay_observation_is_current(value, *, now=None):
    from datetime import datetime, timezone
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        return -300 <= age <= POWERPLAY_CURRENT_HOURS * 3600
    except (ValueError, TypeError, OverflowError):
        return False
