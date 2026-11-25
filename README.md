# AI 비서

네이버 캘린더의 오늘 일정과 관심 뉴스, 콕콕 페이지 확인 서비스의 예약 상태를 한 화면에 모아요. 휴대폰에 아침 알림을 받고 한국어로 들을 수 있어요.

## Windows에서 시작하기

Python 3.11 이상에서 아래 명령을 실행하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe app.py
```

[로컬 브리핑](http://localhost:8080)을 열고 `.data/access-code.txt`에 생성된 접속 코드를 입력하세요. `.env`에 접속 코드를 직접 지정했다면 그 코드를 사용하세요. **지금 확인**을 누르면 설정한 소스에서 오늘 브리핑을 만들어요. `.env`를 바꾼 뒤에는 서버를 다시 실행하세요.

## 데이터 연결

- **에브리타임 시간표** 카이온에서 **학교 시간표**를 열고 요일과 시간 눈금이 보이는 캡처를 올리세요. Windows 서버에서 한국어 OCR로 사진을 읽어 수업 후보를 채웁니다. 캡처와 비교해 과목, 요일, 시간과 강의실을 확인하고 **시간표 저장**을 누르세요. 인식되지 않은 수업은 직접 추가할 수 있어요. 원본 사진은 저장하지 않으며, 확정한 수업 정보는 매주 해당 요일에 표시됩니다. 새 학기에는 저장한 시간표를 갱신하세요.
- **네이버 캘린더** `NAVER_ID`와 `NAVER_APP_PASSWORD`를 `.env`에 입력하세요. 네이버 계정에 2단계 인증을 사용 중이면 [애플리케이션 비밀번호를 발급받아](https://help.naver.com/service/5620/contents/2426?lang=ko&osType=COMMONOS) 넣으세요. 일부 캘린더만 읽으려면 `NAVER_CALENDARS`에 네이버에 표시되는 캘린더 이름을 쉼표로 구분해 입력하세요. AI 비서는 제목과 일시만 저장하고 캘린더에 쓰기 요청을 보내지 않아요.
- **관심 뉴스** `NEWS_FEEDS`에 RSS 주소를, `NEWS_INTERESTS`에 관심 키워드를 쉼표로 구분해 입력하세요. 최근 기사에서 키워드가 맞는 최대 3건을 보여줘요. 뉴스 제목을 누르면 원문이 열려요. **네이버 뉴스**도 함께 보려면 [네이버 클라우드 플랫폼 콘솔](https://console.ncloud.com)의 **NAVER API HUB**에서 서비스 이용 신청 후 **뉴스 검색** Application을 등록하고([안내](https://guide.ncloud-docs.com/docs/apihub-procedure)), 인증 정보의 Client ID와 Client Secret을 `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`에 입력하세요. 관심 키워드마다 네이버 뉴스를 검색해 RSS 기사와 함께 골라요. RSS 없이 네이버 뉴스만 써도 돼요.
- **OpenJarvis** 한국어 뉴스 요약을 사용하려면 [공식 안내](https://github.com/open-jarvis/OpenJarvis/blob/main/docs/deployment/api-server.md)에 따라 OpenJarvis를 설정한 후 `jarvis serve --host 127.0.0.1 --port 8010 --agent simple`로 실행하세요. `.env`에 `OPENJARVIS_URL=http://127.0.0.1:8010`과 설치한 `OPENJARVIS_MODEL`을 입력하세요. 모델에는 뉴스 제목과 RSS 발췌문을 전달해요. 모델 연결 없이도 기사와 RSS 발췌문을 볼 수 있어요.
- **콕콕 페이지 확인 서비스** `KOKKOK_DB`에 기존 `site-booking/booking.db`의 위치를 지정하고, `KOKKOK_WATCH_IDS`에 표시할 항목 ID를 쉼표로 구분해 입력하세요. 아래 명령으로 로컬 DB의 항목 ID를 확인할 수 있어요. AI 비서는 선택한 항목을 읽기 전용으로 조회하고, 콕콕의 마지막 확인 시각을 표시해요. 예약 감시와 열림 알림은 콕콕 서버에서 계속 실행돼요.

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; db=sqlite3.connect('file:../site-booking/booking.db?mode=ro', uri=True); print(*db.execute('select id, name from watches order by id'), sep=chr(10))"
```

## 휴대폰에서 받기

1. 서버의 로컬 포트(기본 `8080`)를 휴대폰이 접근 가능한 고정 HTTPS 주소로 연결하세요. HTTPS 리버스 프록시나 기존 터널을 사용할 수 있어요. `.env`의 `ASSISTANT_ORIGIN`에 그 주소를 지정하고 서버를 다시 시작하세요. `VAPID_CONTACT`에는 운영자 이메일을 `mailto:` 형식으로 지정하세요.
2. iPhone Safari에서 HTTPS 주소의 첫 화면을 열고 **공유 → 홈 화면에 추가**를 선택하세요. **웹 앱으로 열기** 옵션이 보이면 켜고 **추가**를 누르세요. 이후 홈 화면의 **카이온** 아이콘에서 메뉴를 열 수 있어요. Android에서는 Chrome에서 HTTPS 주소를 열면 돼요. [Apple 공식 안내](https://support.apple.com/ko-kr/guide/iphone/iphea86e5236/ios)
3. 접속 코드를 입력한 뒤 **알림 설정 → 휴대폰 알림 켜기 → 테스트 알림**을 누르세요. 메뉴에서 **오늘의 브리핑**, **네이버 일정**, **관심 뉴스**, **콕콕 예약**을 각각 열 수 있어요. 아침 알림은 오늘 브리핑을 바로 열어요. **브리핑 듣기**는 기기의 한국어 음성을 사용해요.

기본 알림 시각은 한국 시간 매일 **07:30**이에요. `BRIEFING_TIME`으로 변경할 수 있어요. 서버는 알림 시각에 켜져 있어야 하고, 그 시각부터 2시간 안에 다시 켜면 늦게라도 생성하고 전송해요. 알림 본문에는 개인 일정 제목을 넣지 않아요. `.env`와 `.data`에는 계정 정보나 개인 브리핑이 저장되므로 공유하지 마세요.

## 로컬 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```
