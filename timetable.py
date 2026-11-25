import base64
import json
import os
import subprocess
from datetime import datetime, time
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


def validate_classes(rows):
    if not isinstance(rows, list) or len(rows) > 60:
        raise ValueError
    classes = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError
        day = row.get("day")
        title = row.get("title")
        room = row.get("room", "")
        start = time.fromisoformat(row["start"])
        end = time.fromisoformat(row["end"])
        if (
            type(day) is not int or not 0 <= day <= 6
            or not isinstance(title, str) or not 0 < len(title.strip()) <= 120
            or not isinstance(room, str) or len(room.strip()) > 80
            or start.tzinfo or end.tzinfo or start.second or end.second
            or start.microsecond or end.microsecond or start >= end
        ):
            raise ValueError
        classes.append({"day": day, "title": title.strip(), "room": room.strip(),
                        "start": start.isoformat(timespec="minutes"), "end": end.isoformat(timespec="minutes")})
    return sorted(classes, key=lambda row: (row["day"], row["start"], row["title"]))


def classes_today(rows, now):
    return [
        {**row, **{
            field: datetime.combine(now.date(), time.fromisoformat(row[field]), now.tzinfo).isoformat()
            for field in ("start", "end")
        }}
        for row in rows if row["day"] == now.weekday()
    ]
