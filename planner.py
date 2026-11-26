import threading
from datetime import datetime, time, timedelta

from life import life_today
from sources import SEOUL, calendar_events, lms_items, optional_source
from timetable import school_today


def covers(item, day):
    """Whether an event from start to end touches `day` (an ISO date); all-day ends are exclusive."""
    first, last = item["start"][:10], item["end"][:10]
    return first <= day and (day < last or first == day)


# Naver CalDAV takes over ten seconds per query, so a range is remembered briefly while views change.
# ponytail: per-process dict with a 10-minute lifetime; move to a shared cache if more users arrive.
NAVER_CACHE = {}
NAVER_LOCK = threading.Lock()


def naver_between(first, days, now):
    key = (first, days)
    with NAVER_LOCK:
        cached = NAVER_CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
    result = optional_source("Naver Calendar", lambda: calendar_events(first, days))
    if result["status"] in ("ok", "partial"):
        with NAVER_LOCK:
            if len(NAVER_CACHE) > 20:
                NAVER_CACHE.clear()
            NAVER_CACHE[key] = (now + timedelta(minutes=10), result)
    return result


def calendar_range(timetable, life_items, first, days, with_naver=True):
    """Everything Kaiyon knows for `days` days from `first`, grouped by date for the calendar views."""
    start = datetime.combine(first, time.min, SEOUL)
    naver = naver_between(first, days, datetime.now(SEOUL)) if with_naver else {"status": "skipped", "items": []}
    lms = optional_source("LMS", lambda: lms_items(start, start + timedelta(days=days)))
    result = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        iso = day.isoformat()
        school = (school_today(timetable, datetime.combine(day, time(7, 30), SEOUL)) if timetable
                  else {"week": None, "classes": [], "routines": []})
        life = life_today(life_items, day)
        result.append({
            "date": iso, "week": school["week"], "classes": school["classes"], "routines": school["routines"],
            # Daily habits would fill every cell, so the calendar only counts them.
            "chores": [item for item in life if item["repeat"] != "daily"],
            "habits": sum(item["repeat"] == "daily" for item in life),
            "naver": [item for item in naver["items"] if covers(item, iso)],
            # A lecture period is shown on the day it closes, like a due date.
            "lms": [item for item in lms["items"] if item["end"][:10] == iso],
        })
    return {"first": first.isoformat(), "days": result, "naver_status": naver["status"], "lms_status": lms["status"]}
