const weekdays = ["월", "화", "수", "목", "금", "토", "일"];

const kinds = { class: "수업", work: "근로" };
// Rows saved before kinds existed have no kind and are classes.
const ofKind = (rows, kind) => (rows ?? []).filter(row => (row.kind ?? "class") === kind);

function schoolCard() {
  const card = node("section", null, "card");
  card.append(node("h2", "오늘 학교"));
  if (!schoolToday?.length) {
    card.append(node("p", schoolToday ? "오늘 등록된 수업과 근로가 없어요." : "등록한 시간표가 없어요.", "muted"));
    return card;
  }
  for (const [kind, label] of Object.entries(kinds)) {
    const items = ofKind(schoolToday, kind);
    if (!items.length) continue;
    card.append(node("h3", label));
    const list = node("ul");
    for (const item of items) {
      const row = node("li");
      const start = timeFormat.format(new Date(item.start));
      const end = timeFormat.format(new Date(item.end));
      row.append(node("strong", item.title), node("span", `${start} ~ ${end}${item.room ? ` · ${item.room}` : ""}`, "detail"));
      list.append(row);
    }
    card.append(list);
  }
  return card;
}

function timetableCandidates(canvas, words) {
  const centerX = word => word.x + word.w / 2;
  const centerY = word => word.y + word.h / 2;
  const headers = words.filter(word => /^[월화수목금토일](요일)?$/.test(word.text));
  const monday = headers.find(word => word.text.startsWith("월") &&
    headers.some(other => other.text.startsWith("금") && Math.abs(centerY(word) - centerY(other)) < word.h));
  if (!monday) return [];
  const days = weekdays.map(day => headers.find(word => word.text.startsWith(day) &&
    Math.abs(centerY(word) - centerY(monday)) < monday.h));
  const friday = days[4];
  const width = (centerX(friday) - centerX(monday)) / 4;
  if (width < 20 || days.slice(0, 5).some((day, i) => day &&
    Math.abs(centerX(day) - centerX(monday) - i * width) > width * .2)) return [];
  const ticks = words.filter(word => /^\d{1,2}(?::00|시)?$/.test(word.text) &&
    centerX(word) < centerX(monday) - width * .52 && word.y > monday.y && parseInt(word.text, 10) <= 24)
    .sort((a, b) => a.y - b.y);
  const spacing = [];
  for (let i = 1; i < ticks.length; i++) {
    const before = parseInt(ticks[i - 1].text, 10);
    const after = parseInt(ticks[i].text, 10);
    if (after === before + 1 || (before === 12 && after === 1)) spacing.push(ticks[i].y - ticks[i - 1].y);
  }
  if (!spacing.length) return [];
  spacing.sort((a, b) => a - b);
  const hourHeight = spacing[Math.floor(spacing.length / 2)];
  if (hourHeight < 18) return [];
  const first = ticks[0];
  const firstHour = parseInt(first.text, 10);
  const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
  const rgb = (x, y) => pixels.subarray((Math.floor(y) * canvas.width + Math.floor(x)) * 4,
    (Math.floor(y) * canvas.width + Math.floor(x)) * 4 + 3);
  const distance = (a, b) => Math.max(...a.map((value, i) => Math.abs(value - b[i])));
  // Weekday columns have the same scale. Sample near each edge to avoid text in the middle.
  const top = Math.max(monday.y + monday.h, Math.round(first.y - first.h * .25));
  const bottom = Math.min(canvas.height, Math.round(ticks.at(-1).y + hourHeight));
  const toTime = y => {
    const minutes = Math.min(1439, Math.max(0, firstHour * 60 + Math.round((y - top) * 12 / hourHeight) * 5));
    return [Math.floor(minutes / 60), minutes % 60].map(part => String(part).padStart(2, "0")).join(":");
  };
  const rows = [];
  for (let day = 0; day < days.length; day++) {
    if (day > 4 && !days[day]) continue;
    const center = centerX(monday) + day * width;
    const left = center - width / 2;
    const right = center + width / 2;
    if (left < 1 || right >= canvas.width) continue;
    let start = top;
    let color = null;
    for (let y = top; y <= bottom; y++) {
      let sample = null;
      if (y < bottom) {
        const a = rgb(left + width * .045, y);
        const b = rgb(right - width * .045, y);
        const saturation = Math.max(...b) - Math.min(...b);
        if (distance(a, b) < 12 && saturation >= 13) sample = b;
      }
      if (sample && color && distance(sample, color) < 12) continue;
      if (color && y - start >= hourHeight * .23) {
        const inside = words.filter(word => centerX(word) >= left && centerX(word) < right &&
          centerY(word) >= start && centerY(word) < y);
        if (inside.length) {
          const last = inside.at(-1);
          const room = last.y > inside[0].y + inside[0].h * .65 && /\d/.test(last.text) ? last.text : "";
          const title = (room ? inside.slice(0, -1) : inside).map(word => word.text).join(" ");
          rows.push({ day, kind: title.includes("근로") ? "work" : "class", title, room, start: toTime(start), end: toTime(y) });
        }
      }
      start = y;
      color = sample;
    }
  }
  return rows.slice(0, 60);
}

function addClassRow(row = {}) {
  const field = node("fieldset", null, "class-edit");
  const legend = node("legend");
  field.append(legend);
  function labeled(labelText, control) {
    const label = node("label", labelText);
    label.append(control);
    return label;
  }
  function input(name, type, label, maxLength) {
    const control = node("input");
    control.name = name;
    control.type = type;
    control.value = row[name] ?? "";
    control.required = name !== "room";
    if (maxLength) control.maxLength = maxLength;
    return labeled(label, control);
  }
  const day = node("select");
  day.name = "day";
  weekdays.forEach((name, index) => day.append(new Option(`${name}요일`, index)));
  day.value = row.day ?? 0;
  const kind = node("select");
  kind.name = "kind";
  for (const [value, label] of Object.entries(kinds)) kind.append(new Option(label, value));
  kind.value = row.kind ?? "class";
  const showKind = () => { legend.textContent = kinds[kind.value]; };
  kind.addEventListener("change", showKind);
  showKind();
  const times = node("div", null, "class-times");
  times.append(input("start", "time", "시작"), input("end", "time", "종료"));
  const remove = node("button", "삭제", "secondary");
  remove.type = "button";
  remove.addEventListener("click", () => field.remove());
  field.append(labeled("구분", kind), labeled("요일", day), input("title", "text", "이름", 120), times,
    input("room", "text", "장소 (선택)", 80), remove);
  $("timetable-rows").append(field);
}

function clearTimetableEditor() {
  const form = $("timetable");
  delete form.dataset.loaded;
  form.reset();
  $("timetable-rows").replaceChildren();
  $("timetable-status").textContent = "";
  $("timetable-text").hidden = true;
  const canvas = $("timetable-preview");
  canvas.hidden = true;
  canvas.width = 0;
}

function setTimetableBusy(busy) {
  for (const control of $("timetable").elements) control.disabled = busy;
}

async function loadTimetableEditor() {
  const form = $("timetable");
  if (form.dataset.loaded) return;
  const ticket = String(performance.now());
  form.dataset.loaded = ticket;
  setTimetableBusy(true);
  try {
    const { classes } = await api("/api/timetable");
    if (form.dataset.loaded !== ticket) return;
    classes.forEach(addClassRow);
    $("timetable-status").textContent = "";
    setTimetableBusy(false);
  } catch (error) {
    if (form.dataset.loaded === ticket) {
      delete form.dataset.loaded;
      $("timetable-status").textContent = error.message;
    }
  }
}

function initializeTimetable() {
  $("timetable-add").addEventListener("click", () => {
    if ($("timetable-rows").children.length >= 60) return;
    addClassRow();
    $("timetable-rows").lastElementChild.querySelector('[name="title"]').focus();
  });
  $("timetable").addEventListener("submit", async event => {
    event.preventDefault();
    const status = $("timetable-status");
    const classes = [...$("timetable-rows").children].map(field => Object.fromEntries(
      [...field.querySelectorAll("input, select")].map(input => [input.name, input.name === "day" ? Number(input.value) : input.value])));
    setTimetableBusy(true);
    try {
      await api("/api/timetable", { classes });
      status.textContent = `수업 ${ofKind(classes, "class").length}개, 근로 ${ofKind(classes, "work").length}개를 저장했어요.`;
      await load();
    } catch (error) { status.textContent = error.message; }
    finally { setTimetableBusy(false); }
  });
  $("timetable-photo").addEventListener("change", async event => {
    const input = event.target;
    const photo = input.files[0];
    if (!photo) return;
    const ticket = $("timetable").dataset.loaded;
    const status = $("timetable-status");
    const preview = $("timetable-preview");
    const recognized = $("timetable-text");
    setTimetableBusy(true);
    status.textContent = "사진을 읽고 있어요…";
    preview.hidden = true;
    recognized.hidden = true;
    try {
      if (photo.size > 20 * 1024 * 1024) throw new Error("20MB 이하 사진을 선택해 주세요.");
      const image = await createImageBitmap(photo);
      if ($("timetable").dataset.loaded !== ticket) { image.close(); return; }
      const scale = Math.min(1, 1600 / Math.max(image.width, image.height));
      preview.width = Math.max(1, Math.round(image.width * scale));
      preview.height = Math.max(1, Math.round(image.height * scale));
      preview.getContext("2d").drawImage(image, 0, 0, preview.width, preview.height);
      image.close();
      preview.hidden = false;
      const png = await new Promise(resolve => preview.toBlob(resolve, "image/png"));
      if (!png || png.size > 4 * 1024 * 1024) throw new Error("시간표 부분만 잘라서 다시 올려 주세요.");
      const result = await api("/api/timetable/photo", png);
      if ($("timetable").dataset.loaded !== ticket) return;
      recognized.querySelector("p").textContent = result.text;
      recognized.hidden = !result.text;
      const candidates = timetableCandidates(preview, result.words);
      if (candidates.length) {
        $("timetable-rows").replaceChildren();
        candidates.forEach(addClassRow);
        status.textContent = `${candidates.length}개 칸을 찾았어요. 원본과 비교해 구분, 이름, 요일, 시간을 확인하고 저장해 주세요.`;
      } else {
        status.textContent = "수업 칸을 찾지 못했어요. 사진을 보면서 수업을 추가하거나 요일과 시간 눈금이 보이는 캡처를 올려 주세요.";
      }
    } catch (error) {
      if ($("timetable").dataset.loaded === ticket) status.textContent = error.message;
    } finally {
      input.value = "";
      if ($("timetable").dataset.loaded === ticket) setTimetableBusy(false);
    }
  });
}
