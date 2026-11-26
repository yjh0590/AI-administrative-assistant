let reviewLoaded = 0;

const reviewDay = value => shortDateFormat.format(new Date(`${value}T00:00:00+09:00`));
const reviewTime = value => timeFormat.format(new Date(value));

function reviewList(rows) {
  const list = node("ul");
  for (const [title, detail] of rows) {
    const row = node("li");
    row.append(node("strong", title));
    if (detail) row.append(node("span", detail, "detail"));
    list.append(row);
  }
  return list;
}

function reviewCards(data) {
  const lms = node("section", null, "card");
  lms.append(node("h2", "다음 주 LMS 마감·수강 기간"));
  const notice = sourceNotice("lms", data.lms);
  if (notice) lms.append(node("p", notice, "muted"));
  if (data.lms.items.length) lms.append(reviewList(data.lms.items.map(item => [item.title, lmsLabel(item)])));

  const days = data.days.map(day => {
    const card = node("section", null, "card");
    card.append(node("h2", `${reviewDay(day.date)}${day.week ? ` · ${day.week}주차` : ""}`));
    const rows = [
      ...day.classes.map(item => {
        const kind = kinds[item.kind] ?? "수업";
        // "근로" rows are already named after their kind, so skip the repeated label.
        return [item.title, [item.title.startsWith(kind) ? "" : kind, `${reviewTime(item.start)} ~ ${reviewTime(item.end)}`, item.room]
          .filter(Boolean).join(" · ")];
      }),
      ...day.routines.map(item => [item.title, ["할 일", item.time].filter(Boolean).join(" · ")]),
      ...day.chores.map(item => [item.title, [item.category, item.zone].filter(Boolean).join(" · ")]),
    ];
    card.append(rows.length ? reviewList(rows) : node("p", "일정 없음", "muted"));
    return card;
  });

  const check = node("section", null, "card");
  check.append(node("h2", "이번 주 정리"));
  const list = node("ul");
  for (const [question, href, label] of [
    ["끝났거나 바뀐 수업·발표·근로가 있나요?", "#school", "시간표 고치기"],
    ["다음 주에 새로 생긴 할 일이 있나요?", "#school", "일상 규칙 추가"],
    ["청소 일정을 바꿀 게 있나요?", "#life", "생활 캘린더 열기"],
  ]) {
    const row = node("li");
    const link = node("a", label);
    link.href = href;
    const action = node("span", null, "detail");
    action.append(link);
    row.append(node("strong", question), action);
    list.append(row);
  }
  check.append(list);
  return [lms, ...days, check];
}

// The preview reads live LMS data, so reload it at most once a minute while the page stays open.
async function loadReview(force = false) {
  const box = $("review");
  if (!force && Date.now() - reviewLoaded < 60_000) return;
  reviewLoaded = Date.now();
  box.replaceChildren(node("p", "다음 주 일정을 모으고 있어요…", "card muted"));
  try {
    box.replaceChildren(...reviewCards(await api("/api/review")));
  } catch (error) {
    reviewLoaded = 0;
    box.replaceChildren(node("p", error.message, "card muted"));
  }
}
