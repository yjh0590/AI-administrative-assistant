import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

LMS_HOST = "lms.inu.ac.kr"


def text(value, longest, required=True):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError
    return value.strip()[:longest]


def day(value, required=True):
    if value is None and not required:
        return ""
    return date.fromisoformat(text(value, 10)).isoformat()


def moment(value):
    if value is None:
        return ""
    parsed = datetime.fromisoformat(text(value, 40))
    if not parsed.tzinfo:
        raise ValueError
    return parsed.isoformat()


def lms_url(value):
    url = urlsplit(text(value, 500))
    if url.scheme != "https" or url.hostname != LMS_HOST:
        raise ValueError
    return url.geturl()


def listed(value, longest):
    if not isinstance(value, list) or len(value) > longest:
        raise ValueError
    return value


def validate_sync(body):
    """Keep only the fields the briefing uses from an extension upload; full notice bodies are dropped."""
    courses = []
    for course in listed(body.get("courses"), 40):
        notices = [{
            "title": text(notice.get("title"), 300), "posted": day(notice.get("posted")), "url": lms_url(notice.get("url")),
            "excerpt": text(notice.get("excerpt"), 300, required=False),
        } for notice in listed(course.get("notices", []), 30)]
        weeks = []
        for week in listed(course.get("weeks", []), 30):
            if type(week.get("week")) is not int or week.get("online") not in (True, False, None):
                raise ValueError
            weeks.append({
                "week": week["week"], "start": day(week.get("start"), False), "end": day(week.get("end"), False),
                "online": week["online"],
                "activities": [{"title": text(item.get("title"), 200), "open": moment(item.get("open")),
                                "close": moment(item.get("close"))} for item in listed(week.get("activities", []), 30)],
            })
        courses.append({
            # LMS names carry the section code, e.g. "재무행정론 (CFB6008001)"; the timetable uses the bare name.
            "name": re.sub(r"\s+\([^()]*\)$", "", text(course.get("name"), 200)),
            "url": lms_url(course.get("url")), "notices": notices, "weeks": weeks,
        })
    return {"synced": moment(body.get("synced")), "courses": courses}


def sync_today(sync, today):
    """New notices from the last two days and courses whose LMS week today has video lectures."""
    if not sync:
        return None
    recent = (today - timedelta(days=1)).isoformat()
    notices = sorted(({**notice, "course": course["name"]} for course in sync["courses"] for notice in course["notices"]
                      if notice["posted"] >= recent), key=lambda notice: notice["posted"], reverse=True)
    iso = today.isoformat()
    online = [course["name"] for course in sync["courses"] for week in course["weeks"]
              if week["online"] and week["start"] and week["end"] and week["start"] <= iso <= week["end"]]
    stale = datetime.fromisoformat(sync["synced"]).date() < today - timedelta(days=2) if sync["synced"] else True
    return {"synced": sync["synced"], "stale": stale, "notices": notices, "online": online}
