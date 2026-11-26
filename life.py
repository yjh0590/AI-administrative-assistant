REPEATS = ("daily", "weekly", "biweekly", "monthly", "seasonal", "yearly")
SEASON_MONTHS = (3, 6, 9, 12)


def chore(zone, title, repeat, weekday=None, day=None, month=None):
    return {"category": "청소", "zone": zone, "title": title, "repeat": repeat,
            "weekday": weekday, "day": day, "month": month}


# A one-room cleaning plan. Weekly jobs are spread Mon-Sun and monthly or seasonal jobs across dates
# so no single day piles up. Weekdays are 0=Mon ... 6=Sun.
DEFAULT_ITEMS = [
    chore("주방", "설거지, 음식물 거름망 비우기, 조리대에 튄 물·기름 닦기", "daily"),
    chore("주방", "가스레인지·인덕션, 싱크대, 주방 바닥 닦기", "weekly", weekday=0),
    chore("주방", "전자레인지 안, 쓰레기통 안, 냉장고에서 오염된 칸 닦기", "monthly", day=1),
    chore("주방", "냉장고 선반 전체, 후드 필터 청소", "seasonal", day=7),
    chore("화장실", "샤워 후 환기, 배수구에 보이는 머리카락 걷기", "daily"),
    chore("화장실", "변기·세면대·발매트 관리", "weekly", weekday=1),
    chore("화장실", "바닥과 배수구 덮개 닦기", "biweekly", weekday=5),
    chore("화장실", "거울·수전 물때, 샴푸 선반 밑 닦기", "monthly", day=5),
    chore("화장실", "줄눈·실리콘·환풍구 겉면 상태 확인하고 청소", "seasonal", day=14),
    chore("침대·옷장", "벗은 옷을 옷걸이나 빨래통에 넣기", "daily"),
    chore("침대·옷장", "베개커버 교체 (땀이나 유분이 많이 묻었을 때)", "weekly", weekday=5),
    chore("침대·옷장", "시트·이불 커버 교체", "biweekly", weekday=5),
    chore("침대·옷장", "침대 밑과 옷장 앞 먼지 제거", "monthly", day=10),
    chore("침대·옷장", "이불 세탁·교체", "seasonal", day=21),
    chore("침대·옷장", "옷장 안과 위쪽 닦기", "yearly", day=5, month=10),
    chore("책상·생활공간", "컵·포장지 치우기", "daily"),
    chore("책상·생활공간", "책상·손 닿는 선반 닦고 청소기 돌리기", "weekly", weekday=2),
    chore("책상·생활공간", "물걸레질", "biweekly", weekday=6),
    chore("책상·생활공간", "모니터 받침대 아래, 책상 뒤 케이블 주변 먼지 제거", "monthly", day=15),
    chore("책상·생활공간", "옮길 수 있는 가구 뒤쪽과 높은 선반 청소", "yearly", day=20, month=12),
    chore("현관·신발장", "젖은 신발 펴서 말리기", "daily"),
    chore("현관·신발장", "현관 바닥 모래·먼지 쓸기", "weekly", weekday=3),
    chore("현관·신발장", "신발장 아래칸과 문턱 닦기", "monthly", day=20),
    chore("현관·신발장", "신발을 꺼내고 선반 전체 닦기", "seasonal", day=28),
    chore("세탁기 주변", "세탁 후 문 주변 물기 확인하고 말리기", "daily"),
    chore("세탁기 주변", "빨래통 주변 먼지·보풀 치우기", "weekly", weekday=4),
    chore("세탁기 주변", "세제통과 문 주변 닦기. 통세척·필터는 제품 설명서에 맞춰 관리", "monthly", day=25),
    chore("세탁기 주변", "세탁기 옆 틈과 주변 바닥 청소", "seasonal", day=10),
    chore("창가·에어컨", "창에 결로가 맺혔을 때 물기 닦기", "daily"),
    chore("창가·에어컨", "창턱에 쌓인 먼지 닦기", "biweekly", weekday=6),
    chore("창가·에어컨", "창틀 확인하고 먼지가 쌓였으면 닦기", "monthly", day=28),
    chore("창가·에어컨", "창틀 청소", "seasonal", day=17),
    chore("창가·에어컨", "냉방 시작 전 에어컨 필터 확인", "yearly", day=1, month=5),
    chore("창가·에어컨", "커튼이나 블라인드 청소", "yearly", day=5, month=4),
]


def number(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError
    return value


def label(value, longest, required=True):
    if not isinstance(value, str) or len(value.strip()) > longest or (required and not value.strip()):
        raise ValueError
    return value.strip()


def validate_items(rows):
    if not isinstance(rows, list) or len(rows) > 150:
        raise ValueError
    items = []
    for row in rows:
        if not isinstance(row, dict) or row.get("repeat") not in REPEATS:
            raise ValueError
        repeat = row["repeat"]
        items.append({
            "category": label(row.get("category"), 30), "zone": label(row.get("zone", ""), 30, False),
            "title": label(row.get("title"), 200), "repeat": repeat,
            "weekday": number(row.get("weekday"), 0, 6) if repeat in ("weekly", "biweekly") else None,
            # Days stop at 28 so monthly jobs happen in February too.
            "day": number(row.get("day"), 1, 28) if repeat in ("monthly", "seasonal", "yearly") else None,
            "month": number(row.get("month"), 1, 12) if repeat == "yearly" else None,
        })
    return items


def due(item, day):
    repeat = item["repeat"]
    if repeat == "daily":
        return True
    if repeat in ("weekly", "biweekly"):
        # ponytail: biweekly uses even ISO weeks, so a 53-week year repeats a week; store an anchor date if that matters.
        return day.weekday() == item["weekday"] and (repeat == "weekly" or day.isocalendar().week % 2 == 0)
    if day.day != item["day"]:
        return False
    return (repeat == "monthly" or (repeat == "seasonal" and day.month in SEASON_MONTHS)
            or (repeat == "yearly" and day.month == item["month"]))


def life_today(items, day):
    return [item for item in items if due(item, day)]
