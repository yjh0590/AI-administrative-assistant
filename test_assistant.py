import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import feedparser
from icalendar import Calendar

from app import Assistant, create_app
from sources import SEOUL, booking_items, build_briefing, calendar_events, news_items, section, summarize_news


class SourcesTest(unittest.TestCase):
    now = datetime(2026, 11, 25, 7, 30, tzinfo=SEOUL)

    def test_naver_queries_today_and_only_returns_display_fields(self):
        ical = Calendar.from_ical("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:all-day
DTSTART;VALUE=DATE:20261125
SUMMARY:마감
END:VEVENT
BEGIN:VEVENT
UID:meeting
DTSTART:20261125T013000Z
DURATION:PT30M
SUMMARY:회의
DESCRIPTION:Private note
END:VEVENT
BEGIN:VEVENT
UID:tomorrow
DTSTART;VALUE=DATE:20261126
SUMMARY:내일
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART:20261125T020000Z
STATUS:CANCELLED
SUMMARY:취소 일정
END:VEVENT
END:VCALENDAR
""")
        client = MagicMock()
        collection = client.return_value.__enter__.return_value.principal.return_value.calendars.return_value = [Mock()]
        collection[0].get_display_name.return_value = "내 캘린더"
        collection[0].search.return_value = [SimpleNamespace(icalendar_instance=ical)]
        with patch("sources.caldav.DAVClient", client), patch.dict(os.environ, {
            "NAVER_ID": "local-test", "NAVER_APP_PASSWORD": "test", "NAVER_CALENDARS": "내 캘린더"
        }):
            result = calendar_events(self.now.date())
        self.assertEqual(result["status"], "ok")
        all_day, meeting = result["items"]
        self.assertTrue(all_day["all_day"])
        self.assertEqual(meeting, {
            "title": "회의", "start": "2026-11-25T10:30:00+09:00", "end": "2026-11-25T11:00:00+09:00", "all_day": False,
        })
        self.assertEqual(collection[0].search.call_args.kwargs, {
            "event": True, "expand": True,
            "start": datetime(2026, 11, 25, tzinfo=SEOUL), "end": datetime(2026, 11, 26, tzinfo=SEOUL),
        })

    def test_calendar_failure_is_not_an_empty_success(self):
        with patch.dict(os.environ, {"NAVER_ID": "test", "NAVER_APP_PASSWORD": "test"}), patch(
            "sources.caldav.DAVClient", side_effect=OSError
        ), self.assertLogs("sources", "WARNING"):
            result = build_briefing(self.now)
        self.assertEqual(result["agenda"], section("unavailable"))

    def test_news_filters_matches_and_deduplicates(self):
        rss_items = [
            ("New AI chips", "chips"), ("New AI chips!", "duplicate"),
            ("AI models improve", "models"), ("AI policy review", "policy"),
            ("AI lab opens", "lab"), ("Unrelated mail", "mail"),
        ]
        articles = "".join(f"<item><title>{title}</title><link>https://example.test/{slug}</link></item>" for title, slug in rss_items)
        feed = feedparser.parse(f"<rss version='2.0'><channel><title>News</title>{articles}</channel></rss>")
        with patch.dict(os.environ, {"NEWS_FEEDS": "https://example.test", "NEWS_INTERESTS": "AI"}), patch("sources.read_feed", return_value=feed):
            result = news_items(self.now)
        self.assertEqual([entry["title"] for entry in result["items"]], ["New AI chips", "AI models improve", "AI policy review"])

    def test_news_summary_falls_back_when_model_output_is_invalid(self):
        item = {"title": "제목", "summary": "원문 발췌"}
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "[1]"}}]}
        with patch.dict(os.environ, {"OPENJARVIS_URL": "http://localhost:8010", "OPENJARVIS_MODEL": "test"}), patch(
            "sources.requests.post", return_value=response
        ) as post:
            summarize_news([item])
            self.assertEqual(item["summary"], "원문 발췌")
            response.json.return_value = {"choices": [{"message": {"content": '["한국어 요약"]'}}]}
            summarize_news([item])
            self.assertEqual(item["summary"], "한국어 요약")
        self.assertEqual(post.call_args.args[0], "http://localhost:8010/v1/chat/completions")

    def test_kokkok_uses_current_state_and_only_requested_watches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "booking.db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE watches (id, name, url, keyword, state, opened, checked, error)")
            db.executemany("INSERT INTO watches VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (1, "My watch", "https://example.test", "open", "false", 1, 123, None),
                (2, "Other watch", "https://example.test", "open", "true", 1, 123, None),
            ])
            db.commit()
            db.close()
            original = path.read_bytes()
            with patch.dict(os.environ, {"KOKKOK_DB": str(path), "KOKKOK_WATCH_IDS": "1"}):
                result = booking_items()
            self.assertEqual([(item["title"], item["status"]) for item in result["items"]], [("My watch", "예약 조건 대기 중")])
            self.assertEqual(path.read_bytes(), original)


class AssistantTest(unittest.TestCase):
    due = datetime(2026, 11, 25, 7, 30, tzinfo=SEOUL)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.collect = Mock(side_effect=lambda now: {
            "date": now.date().isoformat(), "generated": now.isoformat(),
            "agenda": section("ok"), "news": section("ok"), "bookings": section("ok"),
        })
        self.assistant = Assistant(Path(self.directory.name), time(7, 30), self.collect)
        self.assistant.notify = Mock(return_value=True)
        self.client = create_app(self.assistant, "test-very-long-access-code").test_client()

    def test_auth_and_serve_cached_briefing(self):
        self.assertEqual(self.client.get("/api/briefing").status_code, 401)
        for path in ("/", "/sw.js", "/manifest.webmanifest", "/icon-192.png"):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/session", json={"code": "wrong"}).status_code, 401)
        credentials = {"code": "test-very-long-access-code"}
        self.assertEqual(self.client.post("/api/session", json=credentials, headers={"Origin": "https://other.test"}).status_code, 403)
        self.assertEqual(self.client.post("/api/session", json=credentials).status_code, 200)
        self.assistant.refresh(datetime.now(SEOUL))
        self.assertEqual(self.client.get("/api/briefing").json["briefing"]["agenda"], section("ok"))
        self.assertEqual(self.client.post("/api/logout", json={}).status_code, 200)
        self.assertEqual(self.client.get("/api/briefing").status_code, 401)

    def test_configured_origin_uses_secure_cookie(self):
        client = create_app(self.assistant, "test-very-long-access-code", "https://assistant.example.test").test_client()
        response = client.post("/api/session", base_url="https://assistant.example.test", json={"code": "test-very-long-access-code"})
        self.assertIn("Secure", response.headers["Set-Cookie"])
        self.assertIn("Expires=", response.headers["Set-Cookie"])

    def test_timetable_photo_and_confirmed_classes_are_separate(self):
        photo = {"data": b"\x89PNG\r\n\x1a\nfixture", "content_type": "image/png"}
        self.assertEqual(self.client.post("/api/timetable/photo", **photo).status_code, 401)
        self.client.post("/api/session", json={"code": "test-very-long-access-code"})
        with patch("app.read_photo", return_value={"text": "행정학", "words": []}) as recognize:
            blocked = self.client.post("/api/timetable/photo", headers={"Origin": "https://other.test"}, **photo)
            self.assertEqual(blocked.status_code, 403)
            self.assertEqual(self.client.post("/api/timetable/photo", **photo).json["text"], "행정학")
            recognize.assert_called_once_with(photo["data"])
        self.assertEqual(self.client.get("/api/timetable").json, {"classes": []})
        with patch("app.datetime") as clock:
            clock.now.return_value = self.due
            row = {"day": self.due.weekday(), "start": "09:00", "end": "10:30", "title": "행정학", "room": "101"}
            other_day = {**row, "day": (row["day"] + 1) % 7}
            self.assertEqual(self.client.post("/api/timetable", json={"classes": [row, other_day]}).status_code, 200)
            self.assertEqual(self.client.post("/api/timetable", json={"classes": [{**row, "end": "07:00"}]}).status_code, 400)
            today = self.client.get("/api/briefing").json["school"]
            self.assertEqual(len(today), 1)
            self.assertEqual(today[0]["start"], "2026-11-25T09:00:00+09:00")
            self.assertEqual(today[0]["title"], "행정학")

    def test_kaiyon_portraits_are_served_as_webp(self):
        for variant in ("woman", "man"):
            with self.client.get(f"/kaiyon-{variant}.webp") as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/webp")

    def test_schedule_refreshes_early_preview_and_sends_once(self):
        self.assistant.register({"endpoint": "test-device"})
        self.assistant.refresh(self.due - timedelta(hours=1))
        self.assistant.run_due(self.due - timedelta(minutes=1))
        self.assistant.notify.assert_not_called()
        self.assistant.run_due(self.due)
        self.assistant.run_due(self.due + timedelta(minutes=10))
        self.assertEqual(self.collect.call_count, 2)
        self.assistant.notify.assert_called_once()
        self.assertEqual(self.assistant.briefing(self.due.date().isoformat())["generated"], self.due.isoformat())

    def test_schedule_retries_failed_delivery_without_rebuilding(self):
        self.assistant.register({"endpoint": "test-device"})
        self.assistant.notify.side_effect = [False, True]
        self.assistant.run_due(self.due)
        self.assistant.run_due(self.due + timedelta(minutes=4))
        self.assistant.run_due(self.due + timedelta(minutes=5))
        self.collect.assert_called_once()
        self.assertEqual(self.assistant.notify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
