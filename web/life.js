const repeats = { daily: "매일", weekly: "매주", biweekly: "격주", monthly: "매달", seasonal: "계절마다", yearly: "매년" };

function repeatText(item) {
  if (item.repeat === "daily") return "매일";
  if (item.repeat === "weekly" || item.repeat === "biweekly") return `${repeats[item.repeat]} ${weekdays[item.weekday]}요일`;
  if (item.repeat === "monthly") return `매달 ${item.day}일`;
  if (item.repeat === "seasonal") return `3·6·9·12월 ${item.day}일`;
  return `매년 ${item.month}월 ${item.day}일`;
}

// Daily habits repeat every day, so the briefing folds them away and reads only scheduled jobs aloud.
const plannedLife = () => lifeToday.filter(item => item.repeat !== "daily");

function lifeCard() {
  const card = node("section", null, "card");
  card.append(node("h2", "오늘 생활"));
  if (!lifeToday.length) {
    card.append(node("p", "오늘 할 생활 일정이 없어요.", "muted"));
    return card;
  }
  const list = items => {
    const ul = node("ul");
    for (const item of items) {
      const row = node("li");
      row.append(node("strong", item.title), node("span", [item.zone, repeatText(item)].filter(Boolean).join(" · "), "detail"));
      ul.append(row);
    }
    return ul;
  };
  for (const category of new Set(lifeToday.map(item => item.category))) {
    const items = lifeToday.filter(item => item.category === category);
    const planned = items.filter(item => item.repeat !== "daily");
    const habits = items.filter(item => item.repeat === "daily");
    card.append(node("h3", category));
    if (planned.length) card.append(list(planned));
    if (habits.length) {
      const details = node("details");
      details.append(node("summary", `매일 습관 ${habits.length}개`), list(habits));
      card.append(details);
    }
  }
  return card;
}

function addLifeRow(item = {}) {
  const field = node("fieldset", null, "class-edit");
  const legend = node("legend");
  field.append(legend);
  function control(tag, name, value) {
    const element = node(tag);
    element.name = name;
    if (value !== undefined && value !== null) element.value = value;
    return element;
  }
  const category = control("input", "category", item.category ?? "청소");
  category.required = true;
  category.maxLength = 30;
  category.setAttribute("list", "life-categories");
  const zone = control("input", "zone", item.zone);
  zone.maxLength = 30;
  const title = control("input", "title", item.title);
  title.required = true;
  title.maxLength = 200;
  const repeat = control("select", "repeat");
  for (const [value, text] of Object.entries(repeats)) repeat.append(new Option(text, value));
  repeat.value = item.repeat ?? "weekly";
  const weekday = control("select", "weekday");
  weekdays.forEach((name, index) => weekday.append(new Option(`${name}요일`, index)));
  weekday.value = item.weekday ?? 0;
  const day = control("input", "day", item.day ?? 1);
  day.type = "number";
  day.min = 1;
  day.max = 28;
  const month = control("select", "month");
  for (let value = 1; value <= 12; value++) month.append(new Option(`${value}월`, value));
  month.value = item.month ?? 1;
  const weekdayLabel = labeled("요일", weekday);
  const dayLabel = labeled("날짜 (1~28일)", day);
  const monthLabel = labeled("월", month);
  const showRepeat = () => {
    legend.textContent = `${category.value || "생활"} · ${repeats[repeat.value]}`;
    weekdayLabel.hidden = !["weekly", "biweekly"].includes(repeat.value);
    dayLabel.hidden = !["monthly", "seasonal", "yearly"].includes(repeat.value);
    day.required = !dayLabel.hidden;
    monthLabel.hidden = repeat.value !== "yearly";
  };
  repeat.addEventListener("change", showRepeat);
  category.addEventListener("input", showRepeat);
  showRepeat();
  const remove = node("button", "삭제", "secondary");
  remove.type = "button";
  remove.addEventListener("click", () => field.remove());
  field.append(labeled("카테고리", category), labeled("구역 (선택)", zone), labeled("할 일", title),
    labeled("반복", repeat), weekdayLabel, dayLabel, monthLabel, remove);
  $("life-rows").append(field);
}

function clearLifeEditor() {
  const form = $("life");
  delete form.dataset.loaded;
  form.reset();
  $("life-rows").replaceChildren();
  $("life-status").textContent = "";
}

function setLifeBusy(busy) {
  for (const control of $("life").elements) control.disabled = busy;
}

async function loadLifeEditor() {
  const form = $("life");
  if (form.dataset.loaded) return;
  const ticket = String(performance.now());
  form.dataset.loaded = ticket;
  setLifeBusy(true);
  try {
    const { items } = await api("/api/life");
    if (form.dataset.loaded !== ticket) return;
    items.forEach(addLifeRow);
    setLifeBusy(false);
  } catch (error) {
    if (form.dataset.loaded === ticket) {
      delete form.dataset.loaded;
      $("life-status").textContent = error.message;
    }
  }
}

function initializeLife() {
  $("life-add").addEventListener("click", () => {
    if ($("life-rows").children.length >= 150) return;
    addLifeRow();
    $("life-rows").lastElementChild.querySelector('[name="title"]').focus();
  });
  $("life").addEventListener("submit", async event => {
    event.preventDefault();
    const status = $("life-status");
    const items = [...$("life-rows").children].map(field => {
      const value = name => field.querySelector(`[name="${name}"]`).value;
      return {
        category: value("category"), zone: value("zone"), title: value("title"), repeat: value("repeat"),
        weekday: Number(value("weekday")), day: Number(value("day")), month: Number(value("month")),
      };
    });
    setLifeBusy(true);
    try {
      await api("/api/life", { items });
      status.textContent = `생활 일정 ${items.length}개를 저장했어요.`;
      await load();
    } catch (error) { status.textContent = error.message; }
    finally { setLifeBusy(false); }
  });
}
