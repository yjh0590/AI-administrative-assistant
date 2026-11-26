import base64
import json
import os
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path


def read_photo(image):
    if os.name != "nt":
        raise OSError("Windows OCR is unavailable")
    program = Path(__file__).with_name("timetable_ocr.ps1").read_text(encoding="utf-8")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
         base64.b64encode(program.encode("utf-16le")).decode("ascii")],
        input=base64.b64encode(image), capture_output=True, timeout=25,
        creationflags=subprocess.CREATE_NO_WINDOW, check=True,
    )
    return json.loads(result.stdout)


def clock(value):
    value = time.fromisoformat(value)
    if value.tzinfo or value.second or value.microsecond:
        raise ValueError
    return value


def weeks(value):
    if not isinstance(value, list) or len(value) > 30 or any(type(week) is not int or not 1 <= week <= 30 for week in value):
        raise ValueError
    return sorted(set(value))


def text(value, longest, required=True):
    if not isinstance(value, str) or len(value.strip()) > longest or (required and not value.strip()):
        raise ValueError
    return value.strip()


def validate_classes(rows):
    if not isinstance(rows, list) or len(rows) > 60:
        raise ValueError
    classes = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError
        kind = row.get("kind", "class")
        if kind not in ("class", "work", "online"):
            raise ValueError
        item = {"kind": kind, "title": text(row.get("title"), 120), "room": text(row.get("room", ""), 80, False),
                "off_weeks": weeks(row.get("off_weeks", [])), "day": None, "date": "", "start": "", "end": ""}
        if kind != "online":
            # A dated row happens once on that date (monthly work rosters); otherwise it repeats weekly.
            item["date"] = iso_day(row.get("date", ""))
            day = date.fromisoformat(item["date"]).weekday() if item["date"] else row.get("day")
            start, end = clock(row["start"]), clock(row["end"])
            if type(day) is not int or not 0 <= day <= 6 or start >= end:
                raise ValueError
            item.update(day=day, start=start.isoformat(timespec="minutes"), end=end.isoformat(timespec="minutes"))
        classes.append(item)
    return sorted(classes, key=lambda row: (row["date"], 7 if row["day"] is None else row["day"], row["start"], row["title"]))


def validate_routines(rows, titles):
    if not isinstance(rows, list) or len(rows) > 30:
        raise ValueError
    routines = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError
        days = row.get("days", [])
        if not isinstance(days, list) or any(type(day) is not int or not 0 <= day <= 6 for day in days):
            raise ValueError
        at = row.get("time", "")
        course = text(row.get("course", ""), 120, False)
        if course and course not in titles:
            raise ValueError
        routines.append({"title": text(row.get("title"), 120), "days": sorted(set(days)),
                         "time": clock(at).isoformat(timespec="minutes") if at else "", "course": course})
    return routines


def iso_day(value):
    if not isinstance(value, str) or (value and date.fromisoformat(value).isoformat() != value):
        raise ValueError
    return value


def validate_timetable(body):
    start, last = iso_day(body.get("start", "")), iso_day(body.get("last", ""))
    if start and last and last < start:
        raise ValueError
    classes = validate_classes(body.get("classes"))
    return {"start": start, "last": last, "classes": classes,
            "routines": validate_routines(body.get("routines", []), {row["title"] for row in classes})}


def stored(content):
    # Before rules existed the timetable was saved as a bare list of classes.
    return {"start": "", "classes": content, "routines": []} if isinstance(content, list) else content


def week_of(start, day):
    if not start or day < date.fromisoformat(start):
        return None
    first = date.fromisoformat(start)
    return (day - first + timedelta(days=first.weekday())).days // 7 + 1


def school_today(timetable, now):
    week = week_of(timetable["start"], now.date())
    # After the last class day the term is over: lessons stop, but work shifts may continue.
    ended = bool(timetable.get("last")) and now.date().isoformat() > timetable["last"]
    if ended:
        week = None
    off = {row["title"] for row in timetable["classes"]
           if week in row.get("off_weeks", []) or (ended and row.get("kind") != "work")}
    classes = [
        {**row, **{
            field: datetime.combine(now.date(), time.fromisoformat(row[field]), now.tzinfo).isoformat()
            for field in ("start", "end")
        }}
        for row in timetable["classes"]
        if row.get("kind") != "online" and row["day"] == now.weekday() and week not in row.get("off_weeks", [])
        and row.get("date", "") in ("", now.date().isoformat())
        and not (ended and row.get("kind") != "work")
    ]
    routines = sorted(
        (row for row in timetable["routines"]
         if (not row["days"] or now.weekday() in row["days"]) and row["course"] not in off),
        key=lambda row: (row["time"] or "99", row["title"]),
    )
    return {"week": week, "classes": sorted(classes, key=lambda row: row["start"]), "routines": routines}
