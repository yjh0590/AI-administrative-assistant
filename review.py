from datetime import datetime, time, timedelta

from life import life_today
from sources import SEOUL, lms_items, optional_source
from timetable import school_today


def week_review(timetable, life_items, first):
    """Preview the seven days from `first`: school, routines, scheduled chores and LMS work."""
    days = []
    for offset in range(7):
        day = first + timedelta(days=offset)
        moment = datetime.combine(day, time(7, 30), SEOUL)
        school = school_today(timetable, moment) if timetable else {"week": None, "classes": [], "routines": []}
        days.append({
            "date": day.isoformat(), "week": school["week"], "classes": school["classes"],
            "routines": school["routines"],
            # Daily habits repeat every day, so the preview lists only scheduled chores.
            "chores": [item for item in life_today(life_items, day) if item["repeat"] != "daily"],
        })
    start = datetime.combine(first, time.min, SEOUL)
    lms = optional_source("LMS", lambda: lms_items(start, start + timedelta(days=7)))
    return {"first": first.isoformat(), "days": days, "lms": lms}
