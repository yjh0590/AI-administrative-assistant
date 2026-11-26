from datetime import date, datetime, time, timedelta

from life import life_today
from sources import SEOUL, lms_items, optional_source
from timetable import school_today


def lms_between(first, last):
    start = datetime.combine(first, time.min, SEOUL)
    return optional_source("LMS", lambda: lms_items(start, datetime.combine(last, time.min, SEOUL)))


def month_review(timetable, life_items, first):
    """Preview a whole month: work roster, term dates, monthly or rarer chores and LMS due dates."""
    following = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    days = [first + timedelta(days=offset) for offset in range((following - first).days)]
    rows = (timetable or {}).get("classes", [])
    work = sorted({row["date"] for row in rows if row.get("kind") == "work" and row.get("date", "")[:7] == first.isoformat()[:7]})
    # Weekly chores repeat too often to list here; the weekly preview already shows them.
    chores = [{**item, "date": day.isoformat()} for day in days for item in life_today(life_items, day)
              if item["repeat"] in ("monthly", "seasonal", "yearly")]
    term = [{"title": title, "date": value} for title, value in (("개강일", (timetable or {}).get("start", "")),
                                                                 ("수업 종료일", (timetable or {}).get("last", "")))
            if value[:7] == first.isoformat()[:7]]
    lms = lms_between(first, following)
    lms = {**lms, "items": [item for item in lms["items"] if item["kind"] == "due"]}
    return {"first": first.isoformat(), "work_days": work, "chores": chores, "term": term, "lms": lms}


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
    # When a new month starts within this week, add the monthly check for it.
    starts = [first + timedelta(days=offset) for offset in range(7) if (first + timedelta(days=offset)).day == 1]
    return {"first": first.isoformat(), "days": days, "lms": lms_between(first, first + timedelta(days=7)),
            "month": month_review(timetable, life_items, starts[0]) if starts else None}
