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
from life import DEFAULT_ITEMS, life_today, validate_items
from sources import SEOUL, booking_items, build_briefing, calendar_events, lms_items, news_items, section, summarize_news


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
        with patch.dict(os.environ, {"NEWS_FEEDS": "https://example.test", "NEWS_INTERESTS": "AI", "NAVER_CLIENT_ID": ""}), patch("sources.read_feed", return_value=feed):
            result = news_items(self.now)
        self.assertEqual([entry["title"] for entry in result["items"]], ["New AI chips", "AI models improve", "AI policy review"])

    def test_naver_news_search_uses_interests_without_rss(self):
        fresh = self.now.strftime("%a, %d %b %Y %H:%M:%S +0900")
        response = Mock()
        response.json.return_value = {"items": [
            {"title": "<b>AI</b> &quot;반도체&quot; 투자", "description": "설명", "pubDate": fresh,
             "originallink": "https://press.test/1", "link": "https://n.news.naver.com/1"},
            {"title": "<b>AI</b> 옛 기사", "description": "", "pubDate": "Mon, 01 Jan 2024 09:00:00 +0900",
             "originallink": "https://press.test/2", "link": ""},
        ]}
        env = {"NEWS_FEEDS": "", "NEWS_INTERESTS": "AI", "NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, env), patch("sources.requests.get", return_value=response) as get:
            result = news_items(self.now)
        self.assertEqual(get.call_args.kwargs["params"]["query"], "AI")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"], [{"title": 'AI "반도체" 투자', "summary": "설명",
                                            "url": "https://n.news.naver.com/1", "source": "네이버 뉴스"}])

    def test_lms_keeps_near_due_dates_and_open_lecture_periods(self):
        # now is 2026-11-25 07:30 KST (2026-11-24 22:30 UTC).
        def event(summary, course, start, end):
            return (f"BEGIN:VEVENT\r\nUID:{summary}{course}\r\nSUMMARY:{summary}\r\nCATEGORIES:{course}\r\n"
                    f"DTSTART:{start}\r\nDTEND:{end}\r\nEND:VEVENT\r\n")
        body = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join([
            event("과제2 기한", "재무행정론 (2026-20\\, CFB6008)", "20261126T145900Z", "20261126T145900Z"),
            event("기말 보고서", "재무행정론 (2026-20\\, CFB6008)", "20261210T145900Z", "20261210T145900Z"),
            event("지난 과제", "형사법 (2026-20)", "20261122T145900Z", "20261122T145900Z"),
            event("1차시", "융합교육의 이론과 실제 (2026-20)", "20261123T150000Z", "20261130T145959Z"),
            event("다음 차시", "융합교육의 이론과 실제 (2026-20)", "20261130T150000Z", "20261207T145959Z"),
            event("형성평가 마감", "[한국어] 학과(부)생 폭력예방교육", "20261127T145900Z", "20261127T145900Z"),
            event("Formative evaluation", "[English] Violence Prevention", "20261127T145900Z", "20261127T145900Z"),
        ]) + "END:VCALENDAR\r\n"
        response = Mock(content=body.encode())
        with patch.dict(os.environ, {"LMS_ICAL_URL": "https://lms.example.test/calendar"}), \
                patch("sources.requests.get", return_value=response):
            result = lms_items(self.now)
        self.assertEqual([(item["kind"], item["course"], item["title"]) for item in result["items"]], [
            ("due", "재무행정론", "과제2 기한"),
            ("due", "학과(부)생 폭력예방교육", "형성평가 마감"),
            ("period", "융합교육의 이론과 실제", "1차시"),
        ])
        self.assertEqual(result["items"][0]["end"], "2026-11-26T23:59:00+09:00")

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
        self.assertEqual(self.client.get("/api/timetable").json, {"start": "", "last": "", "classes": [], "routines": []})
        with patch("app.datetime") as clock:
            clock.now.return_value = self.due
            row = {"day": self.due.weekday(), "start": "09:00", "end": "10:30", "title": "행정학", "room": "101"}
            other_day = {**row, "day": (row["day"] + 1) % 7}
            work = {**row, "kind": "work", "start": "13:00", "end": "17:00", "title": "도서관 근로", "room": ""}
            self.assertEqual(self.client.post("/api/timetable", json={"classes": [row, other_day, work]}).status_code, 200)
            self.assertEqual(self.client.post("/api/timetable", json={"classes": [{**row, "end": "07:00"}]}).status_code, 400)
            self.assertEqual(self.client.post("/api/timetable", json={"classes": [{**row, "kind": "club"}]}).status_code, 400)
            today = self.client.get("/api/briefing").json["school"]
            self.assertEqual([item["kind"] for item in today], ["class", "work"])
            self.assertEqual(today[0]["start"], "2026-11-25T09:00:00+09:00")
            self.assertEqual(today[0]["title"], "행정학")

    def test_timetable_rules_skip_off_weeks_and_report_routines(self):
        self.client.post("/api/session", json={"code": "test-very-long-access-code"})
        weekday = self.due.weekday()
        # Timetables saved before rules existed were a bare list.
        self.assistant.save_timetable([{"day": weekday, "kind": "class", "title": "행정학", "room": "",
                                        "start": "09:00", "end": "10:30"}])
        with patch("app.datetime") as clock:
            clock.now.return_value = self.due
            self.assertEqual(self.client.get("/api/briefing").json["school"][0]["title"], "행정학")
            # 2026-09-01 starts week 1, so 2026-11-25 is week 13.
            timetable = {"start": "2026-09-01", "classes": [
                {"day": weekday, "start": "09:00", "end": "10:30", "title": "행정학", "off_weeks": [13]},
                {"day": weekday, "start": "13:00", "end": "14:00", "title": "형사법", "off_weeks": [8]},
                {"kind": "online", "title": "영화와 다문화", "off_weeks": [13]},
                {"kind": "online", "title": "온라인 경제"},
            ], "routines": [
                {"title": "영화와 다문화 듣기", "days": [weekday], "time": "20:00", "course": "영화와 다문화"},
                {"title": "온라인 경제 듣기", "days": [], "time": "", "course": "온라인 경제"},
                {"title": "다른 날 할 일", "days": [(weekday + 1) % 7]},
            ]}
            self.assertEqual(self.client.post("/api/timetable", json=timetable).status_code, 200)
            bad = {**timetable, "routines": [{"title": "듣기", "course": "없는 과목"}]}
            self.assertEqual(self.client.post("/api/timetable", json=bad).status_code, 400)
            result = self.client.get("/api/briefing").json
        self.assertEqual(result["week"], 13)
        self.assertEqual([item["title"] for item in result["school"]], ["형사법"])
        self.assertEqual([item["title"] for item in result["routines"]], ["온라인 경제 듣기"])
        # After the last class day only work shifts and unlinked rules remain. Dated rows happen only on that date.
        work = {"kind": "work", "date": "2026-11-25", "start": "15:00", "end": "17:00", "title": "근로"}
        other = {**work, "date": "2026-12-02", "title": "다음 주 근로"}
        ended = {**timetable, "last": "2026-11-24", "classes": [*timetable["classes"], work, other]}
        with patch("app.datetime") as clock:
            clock.now.return_value = self.due
            self.assertEqual(self.client.post("/api/timetable", json=ended).status_code, 200)
            self.assertEqual(self.client.post("/api/timetable", json={**ended, "last": "2026-08-01"}).status_code, 400)
            result = self.client.get("/api/briefing").json
        self.assertEqual((result["week"], [item["title"] for item in result["school"]]), (None, ["근로"]))
        self.assertEqual(result["routines"], [])

    def test_life_calendar_picks_chores_due_today(self):
        self.assertEqual(validate_items(DEFAULT_ITEMS), DEFAULT_ITEMS)
        titles = lambda day: {item["title"] for item in life_today(DEFAULT_ITEMS, day) if item["repeat"] != "daily"}
        # 2026-11-28 is a Saturday in even ISO week 48; the next Saturday is in odd week 49.
        self.assertIn("시트·이불 커버 교체", titles(datetime(2026, 11, 28).date()))
        self.assertNotIn("시트·이불 커버 교체", titles(datetime(2026, 12, 5).date()))
        self.assertIn("냉장고 선반 전체, 후드 필터 청소", titles(datetime(2026, 12, 7).date()))
        self.assertNotIn("냉장고 선반 전체, 후드 필터 청소", titles(datetime(2027, 1, 7).date()))
        self.assertIn("냉방 시작 전 에어컨 필터 확인", titles(datetime(2027, 5, 1).date()))
        self.client.post("/api/session", json={"code": "test-very-long-access-code"})
        with patch("app.datetime") as clock:
            clock.now.return_value = self.due
            # 2026-11-25 is a Wednesday and the 25th.
            today = {item["title"] for item in self.client.get("/api/briefing").json["life"] if item["repeat"] != "daily"}
            self.assertEqual(today, {"책상·손 닿는 선반 닦고 청소기 돌리기", "세제통과 문 주변 닦기. 통세척·필터는 제품 설명서에 맞춰 관리"})
            mine = [{"category": "장보기", "zone": "", "title": "생수 주문", "repeat": "weekly", "weekday": self.due.weekday()}]
            self.assertEqual(self.client.post("/api/life", json={"items": mine}).status_code, 200)
            self.assertEqual(self.client.post("/api/life", json={"items": [{**mine[0], "repeat": "monthly", "day": 31}]}).status_code, 400)
            self.assertEqual([item["title"] for item in self.client.get("/api/briefing").json["life"]], ["생수 주문"])

    def test_lms_extension_upload_needs_token_and_feeds_briefing(self):
        upload = {"synced": "2026-11-25T06:30:00+09:00", "courses": [{
            "id": "6053", "name": "재무행정론 (CFB6008001)", "url": "https://lms.inu.ac.kr/course/view.php?id=6053",
            "notices": [
                {"title": "11월 25일 수업은 온라인", "posted": "2026-11-24", "url": "https://lms.inu.ac.kr/mod/ubboard/article.php?id=1",
                 "body": "긴 본문" * 500, "excerpt": "녹화 강의로 대체합니다."},
                {"title": "조편성 공지", "posted": "2026-09-26", "url": "https://lms.inu.ac.kr/mod/ubboard/article.php?id=2"},
            ],
            "weeks": [{"week": 13, "start": "2026-11-24", "end": "2026-11-30", "online": True,
                       "activities": [{"type": "vod", "title": "13주차", "open": "2026-11-24T00:00:00+09:00", "close": None}]}],
        }]}
        token = "t" * 40
        extension = {"Origin": "chrome-extension://abcdef"}
        with patch.dict(os.environ, {"LMS_SYNC_TOKEN": token}):
            wrong = self.client.post("/api/lms/import", json=upload, headers={**extension, "Authorization": "Bearer nope"})
            self.assertEqual(wrong.status_code, 401)
            bad = {**upload, "courses": [{**upload["courses"][0], "url": "https://evil.test/course"}]}
            self.assertEqual(self.client.post("/api/lms/import", json=bad, headers={**extension, "Authorization": f"Bearer {token}"}).status_code, 400)
            saved = self.client.post("/api/lms/import", json=upload, headers={**extension, "Authorization": f"Bearer {token}"})
            self.assertEqual(saved.json, {"courses": 1, "synced": "2026-11-25T06:30:00+09:00"})
        self.assertNotIn("body", self.assistant.lms_sync()["courses"][0]["notices"][0])
        self.client.post("/api/session", json={"code": "test-very-long-access-code"})
        with patch("app.datetime") as clock:
            clock.now.return_value = self.due
            sync = self.client.get("/api/briefing").json["lms_sync"]
        self.assertEqual([(item["course"], item["title"]) for item in sync["notices"]], [("재무행정론", "11월 25일 수업은 온라인")])
        self.assertEqual((sync["online"], sync["stale"]), (["재무행정론"], False))

    def test_pc_photo_mode_keeps_timetable_on_server(self):
        client = create_app(self.assistant, "test-very-long-access-code", "", "https://kaiyon.example.test").test_client()
        client.post("/api/session", json={"code": "test-very-long-access-code"})
        server = {"start": "2026-09-01", "last": "", "classes": [], "routines": []}
        with patch("app.requests.Session") as Session:
            session = Session.return_value.__enter__.return_value
            session.request.return_value = Mock(status_code=200, json=Mock(return_value=server))
            self.assertEqual(client.get("/api/timetable").json, server)
            row = {"kind": "class", "day": 0, "start": "09:00", "end": "10:00", "title": "행정학"}
            self.assertEqual(client.post("/api/timetable", json={"classes": [row]}).status_code, 200)
            self.assertEqual(client.post("/api/timetable", json={"classes": [{**row, "end": "08:00"}]}).status_code, 400)
        session.post.assert_called_with("https://kaiyon.example.test/api/session",
                                        json={"code": "test-very-long-access-code"}, timeout=10)
        self.assertEqual(session.request.call_args.args, ("POST", "https://kaiyon.example.test/api/timetable"))
        self.assertIsNone(self.assistant.timetable())

    def test_chat_sends_todays_data_and_explains_failures(self):
        self.client.post("/api/session", json={"code": "test-very-long-access-code"})
        weekday = self.due.weekday()
        self.assistant.save_timetable({"start": "2026-09-01", "last": "", "routines": [], "classes": [
            {"kind": "class", "day": weekday, "date": "", "start": "15:00", "end": "17:45", "title": "행정법", "room": "13-208"}]})
        env = {"AI_BASE_URL": "https://ai.example.test/v1/gateway", "AI_API_KEY": "k", "AI_MODEL": "claude-haiku-5-5", "LMS_ICAL_URL": ""}
        ok = Mock(ok=True, status_code=200, text="", json=Mock(return_value={"choices": [{"message": {"content": "주인님, 오늘은 행정법이 있습니다."}}]}))
        question = {"messages": [{"role": "user", "content": "오늘 수업 뭐야?"}]}
        with patch.dict(os.environ, env), patch("app.datetime") as clock, patch("chat.requests.post", return_value=ok) as post:
            clock.now.return_value = self.due
            self.assertEqual(self.client.post("/api/chat", json=question).json, {"reply": "주인님, 오늘은 행정법이 있습니다."})
            self.assertEqual(self.client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "x"}]}).status_code, 400)
            post.return_value = Mock(ok=False, status_code=402, text='{"error":"insufficient credit"}')
            failed = self.client.post("/api/chat", json=question)
        self.assertEqual(failed.status_code, 503)
        self.assertIn("크레딧", failed.json["error"])
        body = post.call_args_list[0].kwargs["json"]
        self.assertEqual(post.call_args_list[0].args[0], "https://ai.example.test/v1/gateway/chat/completions/")
        self.assertEqual((body["model"], body["messages"][-1]), ("claude-haiku-5-5", {"role": "user", "content": "오늘 수업 뭐야?"}))
        self.assertIn("오늘 수업: 행정법 15:00~17:45 13-208", body["messages"][0]["content"])

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

    def test_sunday_evening_sends_weekly_review_once(self):
        self.assistant.register({"endpoint": "test-device"})
        sunday = datetime(2026, 11, 29, 21, 0, tzinfo=SEOUL)
        self.assistant.run_review(sunday - timedelta(days=1))
        self.assistant.run_review(sunday - timedelta(minutes=1))
        self.assistant.notify.assert_not_called()
        self.assistant.run_review(sunday)
        self.assistant.run_review(sunday + timedelta(minutes=30))
        self.assistant.notify.assert_called_once()
        self.assertEqual(self.assistant.notify.call_args.args[3:], ("weekly-review", "/#review"))
        # 2026-11-29 is the last Sunday of November, so the monthly check rides along.
        self.assertEqual(self.assistant.notify.call_args.args[1], "주간·월간 점검")
        self.client.post("/api/session", json={"code": "test-very-long-access-code"})
        self.assistant.save_timetable({"start": "2026-09-01", "last": "2026-12-14", "routines": [], "classes": [
            {"kind": "class", "day": 0, "date": "", "start": "15:00", "end": "17:45", "title": "형사법", "room": ""},
            {"kind": "work", "day": 1, "date": "2026-12-01", "start": "13:00", "end": "16:00", "title": "근로", "room": ""}]})
        with patch("app.datetime") as clock:
            clock.now.return_value = sunday
            review = self.client.get("/api/review").json
        self.assertEqual([day["date"] for day in review["days"]][::6], ["2026-11-30", "2026-12-06"])
        self.assertEqual((review["days"][0]["week"], review["days"][0]["classes"][0]["title"]), (14, "형사법"))
        self.assertIn("현관 바닥 모래·먼지 쓸기", [item["title"] for item in review["days"][3]["chores"]])
        month = review["month"]
        self.assertEqual((month["first"], month["work_days"], month["term"]),
                         ("2026-12-01", ["2026-12-01"], [{"title": "수업 종료일", "date": "2026-12-14"}]))
        self.assertIn(("2026-12-07", "냉장고 선반 전체, 후드 필터 청소"), [(item["date"], item["title"]) for item in month["chores"]])
        self.assertNotIn("현관 바닥 모래·먼지 쓸기", [item["title"] for item in month["chores"]])

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
