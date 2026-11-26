// Day / week / month calendar over everything Kaiyon knows: timetable, routines, chores, Naver and LMS.
const seoulToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
const isoAdd = (iso, days) => new Date(Date.parse(`${iso}T00:00:00Z`) + days * 864e5).toISOString().slice(0, 10);
const isoWeekday = iso => (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7;
const isoLabel = iso => `${Number(iso.slice(5, 7))}. ${Number(iso.slice(8, 10))}. (${weekdays[isoWeekday(iso)]})`;
const hhmm = value => value.slice(11, 16);

let calView = "week";
let calDate = null;
let calLoaded = "";
try { calView = localStorage.getItem("kaiyon-calendar-view") || "week"; } catch { /* private mode */ }

function calRange() {
  if (calView === "day") return [calDate, 1];
  if (calView === "week") return [isoAdd(calDate, -isoWeekday(calDate)), 7];
  // Month: six full weeks from the Monday on or before the 1st.
  const first = `${calDate.slice(0, 7)}-01`;
  return [isoAdd(first, -isoWeekday(first)), 42];
}

function calEntries(day) {
  return [
    ...day.naver.map(item => ({ kind: "naver", text: item.title, time: item.all_day ? "종일" : hhmm(item.start) })),
    ...day.classes.map(item => ({ kind: item.kind === "work" ? "work" : "class", text: item.title,
      time: `${hhmm(item.start)}~${hhmm(item.end)}`, detail: item.room })),
    ...day.routines.map(item => ({ kind: "routine", text: item.title, time: item.time })),
    ...day.lms.map(item => ({ kind: "lms", text: `${item.course} ${item.title}`, time: `${item.kind === "due" ? "마감" : "수강 끝"} ${hhmm(item.end)}` })),
    ...day.chores.map(item => ({ kind: "chore", text: item.title, detail: item.zone })),
  ].sort((a, b) => (a.time || "99").localeCompare(b.time || "99"));
}

const calKinds = { class: "수업", work: "근로", routine: "할 일", lms: "LMS", naver: "네이버", chore: "청소" };

function calList(day, compact) {
  const entries = calEntries(day);
  if (!entries.length) return node("p", "일정 없음", "muted");
  const list = node("ul", null, "cal-list");
  for (const entry of entries) {
    const row = node("li", null, `cal-${entry.kind}`);
    row.append(node("strong", entry.text));
    const detail = [calKinds[entry.kind], entry.time, compact ? "" : entry.detail].filter(Boolean).join(" · ");
    row.append(node("span", detail, "detail"));
    list.append(row);
  }
  return list;
}

function calDayCard(day, compact) {
  const card = node("section", null, `card cal-day${day.date === seoulToday() ? " cal-today" : ""}`);
  card.append(node("h2", `${isoLabel(day.date)}${day.week ? ` · ${day.week}주차` : ""}`), calList(day, compact));
  if (!compact && day.habits) card.append(node("p", `매일 습관 ${day.habits}개는 생활 캘린더에서 볼 수 있어요.`, "muted"));
  return card;
}

function calMonth(data) {
  const grid = node("div", null, "cal-grid");
  for (const name of weekdays) grid.append(node("span", name, "cal-head"));
  for (const day of data.days) {
    const cell = node("button", null, "cal-cell");
    cell.type = "button";
    if (day.date.slice(0, 7) !== calDate.slice(0, 7)) cell.classList.add("cal-other");
    if (day.date === seoulToday()) cell.classList.add("cal-today");
    cell.append(node("span", String(Number(day.date.slice(8, 10))), "cal-num"));
    const entries = calEntries(day);
    for (const entry of entries.slice(0, 3)) cell.append(node("span", entry.text, `cal-chip cal-${entry.kind}`));
    if (entries.length > 3) cell.append(node("span", `+${entries.length - 3}`, "cal-more"));
    cell.setAttribute("aria-label", `${isoLabel(day.date)} 일정 ${entries.length}개`);
    cell.addEventListener("click", () => { calDate = day.date; setCalView("day"); });
    grid.append(cell);
  }
  return grid;
}

function calToolbar(data) {
  const bar = node("div", null, "cal-toolbar");
  const views = node("div", null, "cal-views");
  for (const [view, label] of [["day", "일"], ["week", "주"], ["month", "월"]]) {
    const button = node("button", label, view === calView ? "" : "secondary");
    button.type = "button";
    button.setAttribute("aria-pressed", String(view === calView));
    button.addEventListener("click", () => setCalView(view));
    views.append(button);
  }
  const step = { day: 1, week: 7 }[calView];
  const move = direction => {
    if (step) calDate = isoAdd(calDate, direction * step);
    else {
      const [year, month] = calDate.split("-").map(Number);
      const next = new Date(Date.UTC(year, month - 1 + direction, 1));
      calDate = next.toISOString().slice(0, 10);
    }
    loadCalendar(true);
  };
  const nav = node("div", null, "cal-nav");
  for (const [label, action, name] of [["‹", () => move(-1), "이전"], ["오늘", () => { calDate = seoulToday(); loadCalendar(true); }, ""],
    ["›", () => move(1), "다음"]]) {
    const button = node("button", label, "secondary");
    button.type = "button";
    if (name) button.setAttribute("aria-label", name);
    button.addEventListener("click", action);
    nav.append(button);
  }
  const title = calView === "month" ? `${calDate.slice(0, 4)}년 ${Number(calDate.slice(5, 7))}월`
    : calView === "week" ? `${isoLabel(data.days[0].date)} ~ ${isoLabel(data.days[6].date)}` : isoLabel(calDate);
  bar.append(views, node("h2", title, "cal-title"), nav);
  return bar;
}

function setCalView(view) {
  calView = view;
  try { localStorage.setItem("kaiyon-calendar-view", view); } catch { /* private mode */ }
  loadCalendar(true);
}

async function loadCalendar(force = false) {
  calDate ??= seoulToday();
  const [start, days] = calRange();
  const key = `${calView}:${start}:${days}`;
  if (!force && calLoaded === key) return;
  calLoaded = key;
  const box = $("calendar-view");
  box.replaceChildren(node("p", "일정을 모으고 있어요…", "card muted"));
  const draw = data => {
    const notes = [];
    if (data.naver_status === "skipped") notes.push("네이버 일정을 불러오는 중이에요…");
    if (data.naver_status === "unavailable") notes.push("네이버 일정을 가져오지 못했어요.");
    if (data.lms_status === "unavailable") notes.push("LMS 일정을 가져오지 못했어요.");
    const body = calView === "month" ? [calMonth(data)]
      : calView === "week" ? data.days.map(day => calDayCard(day, true)) : [calDayCard(data.days[0], false)];
    box.replaceChildren(calToolbar(data), ...notes.map(text => node("p", text, "muted")), ...body);
  };
  try {
    // Naver CalDAV is slow, so draw everything else first and fill Naver events in when they arrive.
    const quick = await api(`/api/calendar?start=${start}&days=${days}&naver=0`);
    if (calLoaded !== key) return;
    draw(quick);
    const full = await api(`/api/calendar?start=${start}&days=${days}`);
    if (calLoaded === key) draw(full);
  } catch (error) {
    calLoaded = "";
    box.replaceChildren(node("p", error.message, "card muted"));
  }
}
