const weekdays = ["월", "화", "수", "목", "금", "토", "일"];

const kinds = { class: "수업", work: "근로", online: "온라인 수업" };
// Rows saved before kinds existed have no kind and are classes.
const ofKind = (rows, kind) => (rows ?? []).filter(row => (row.kind ?? "class") === kind);

function schoolCard() {
  const card = node("section", null, "card");
  card.append(node("h2", schoolWeek ? `오늘 학교 · ${schoolWeek}주차` : "오늘 학교"));
  if (!schoolToday?.length && !schoolRoutines.length) {
    card.append(node("p", schoolToday ? "오늘 등록된 수업과 근로가 없어요." : "등록한 시간표가 없어요.", "muted"));
    return card;
  }
  const section = (label, items, detail) => {
    if (!items.length) return;
    card.append(node("h3", label));
    const list = node("ul");
    for (const item of items) {
      const row = node("li");
      row.append(node("strong", item.title), node("span", detail(item), "detail"));
      list.append(row);
    }
    card.append(list);
  };
  for (const kind of ["class", "work"]) {
    // A course whose LMS week has video lectures may be online instead of in the room this week.
    section(kinds[kind], ofKind(schoolToday, kind), item => `${timeFormat.format(new Date(item.start))} ~ ${
      timeFormat.format(new Date(item.end))}${item.room ? ` · ${item.room}` : ""}${
      lmsSync?.online.includes(item.title) ? " · 이번 주 LMS 동영상 수업" : ""}`);
  }
  section("오늘 할 일", schoolRoutines, item => [item.time, item.course].filter(Boolean).join(" · "));
  return card;
}

// blockWords come from a white-text-only copy of the photo, which reads white labels on colored blocks.
function timetableCandidates(canvas, words, blockWords = words) {
  const centerX = word => word.x + word.w / 2;
  const centerY = word => word.y + word.h / 2;
  const headers = words.filter(word => /^[월화수목금토일](요일)?$/.test(word.text));
  const sameRow = (a, b) => Math.abs(centerY(a) - centerY(b)) < a.h;
  // OCR often misses some gray weekday labels, so Monday plus any other weekday sets the column width.
  const monday = headers.find(word => word.text.startsWith("월") &&
    headers.some(other => !other.text.startsWith("월") && sameRow(word, other)));
  if (!monday) return [];
  const days = weekdays.map(day => headers.find(word => word.text.startsWith(day) && sameRow(monday, word)));
  const steps = days.map((day, i) => day && i ? (centerX(day) - centerX(monday)) / i : null)
    .filter(Boolean).sort((a, b) => a - b);
  const width = steps[Math.floor(steps.length / 2)];
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
    let gap = 0;
    for (let y = top; y <= bottom; y++) {
      let sample = null;
      if (y < bottom) {
        const a = rgb(left + width * .045, y);
        const b = rgb(right - width * .045, y);
        const colored = pixel => Math.max(...pixel) - Math.min(...pixel) >= 13;
        // White labels can cover one edge; use the other edge's block color there.
        if (colored(a) && colored(b)) sample = distance(a, b) < 12 ? b : null;
        else if (colored(a) || colored(b)) sample = colored(a) ? a : b;
      }
      if (sample && color && distance(sample, color) < 12) { gap = 0; continue; }
      // Text strokes and JPEG noise blank a few rows inside a block; only a longer blank ends it.
      if (!sample && color && y < bottom && ++gap < hourHeight * .2) continue;
      const end = y - gap;
      gap = 0;
      if (color && end - start >= hourHeight * .23) {
        const within = list => list.filter(word => centerX(word) >= left && centerX(word) < right &&
          centerY(word) >= start && centerY(word) < end);
        const inside = within(blockWords).length ? within(blockWords) : within(words);
        if (inside.length) {
          const last = inside.at(-1);
          const room = last.y > inside[0].y + inside[0].h * .65 && /\d/.test(last.text) ? last.text : "";
          // Titles wrap mid-word, so wrapped lines join without a space.
          const title = (room ? inside.slice(0, -1) : inside).map((word, i, list) =>
            (i && word.y < list[i - 1].y + list[i - 1].h * .5 ? " " : "") + word.text).join("");
          rows.push({ day, kind: title.includes("근로") ? "work" : "class", title, room, start: toTime(start), end: toTime(end) });
        }
      }
      start = y;
      color = sample;
    }
  }
  return rows.slice(0, 60);
}

function labeled(labelText, control) {
  const label = node("label", labelText);
  label.append(control);
  return label;
}

const weekList = text => [...new Set((text.match(/\d+/g) ?? []).map(Number))];
const editorTitles = () => [...new Set([...$("timetable-rows").querySelectorAll('[name="title"]')]
  .map(input => input.value.trim()).filter(Boolean))];

function addClassRow(row = {}) {
  const field = node("fieldset", null, "class-edit");
  const legend = node("legend");
  field.append(legend);
  function input(name, type, label, maxLength) {
    const control = node("input");
    control.name = name;
    control.type = type;
    control.value = row[name] ?? "";
    control.required = name === "title";
    if (maxLength) control.maxLength = maxLength;
    return labeled(label, control);
  }
  const day = node("select");
  day.name = "day";
  weekdays.forEach((name, index) => day.append(new Option(`${name}요일`, index)));
  day.value = row.day ?? 0;
  const dayLabel = labeled("요일", day);
  const kind = node("select");
  kind.name = "kind";
  for (const [value, label] of Object.entries(kinds)) kind.append(new Option(label, value));
  kind.value = row.kind ?? "class";
  const times = node("div", null, "class-times");
  times.append(input("start", "time", "시작"), input("end", "time", "종료"));
  const dateLabel = input("date", "date", "특정 날짜 (선택, 넣으면 그날만)");
  const dated = dateLabel.querySelector("input");
  // Online classes have no fixed slot, so they skip day and time. Dated rows take their weekday from the date.
  const showKind = () => {
    const online = kind.value === "online";
    legend.textContent = kinds[kind.value];
    dateLabel.hidden = times.hidden = online;
    dayLabel.hidden = online || Boolean(dated.value);
    for (const control of times.querySelectorAll("input")) control.required = !online;
  };
  kind.addEventListener("change", showKind);
  dated.addEventListener("input", showKind);
  showKind();
  const offWeeks = input("off_weeks", "text", "쉬는 주차 (선택, 예: 8, 15)", 120);
  offWeeks.querySelector("input").value = (row.off_weeks ?? []).join(", ");
  const remove = node("button", "삭제", "secondary");
  remove.type = "button";
  remove.addEventListener("click", () => field.remove());
  field.append(labeled("구분", kind), dateLabel, dayLabel, input("title", "text", "이름", 120), times,
    input("room", "text", "장소 (선택)", 80), offWeeks, remove);
  $("timetable-rows").append(field);
}

function addRoutineRow(row = {}) {
  const field = node("fieldset", null, "class-edit");
  field.append(node("legend", "일상 규칙"));
  const title = node("input");
  title.name = "title";
  title.required = true;
  title.maxLength = 120;
  title.placeholder = "예: 온라인 강의 듣기";
  title.value = row.title ?? "";
  const days = node("div", null, "routine-days");
  weekdays.forEach((name, index) => {
    const box = node("input");
    box.type = "checkbox";
    box.name = "days";
    box.value = index;
    box.checked = row.days?.includes(index) ?? false;
    days.append(labeled(name, box));
  });
  const at = node("input");
  at.name = "time";
  at.type = "time";
  at.value = row.time ?? "";
  const course = node("select");
  course.name = "course";
  let chosen = row.course ?? "";
  // Offer the titles currently in the editor, including rows added after this rule.
  const refresh = () => {
    course.replaceChildren(new Option("없음", ""), ...editorTitles().map(name => new Option(name, name)));
    course.value = chosen;
  };
  course.addEventListener("change", () => { chosen = course.value; });
  course.addEventListener("focus", refresh);
  course.addEventListener("pointerdown", refresh);
  refresh();
  const remove = node("button", "삭제", "secondary");
  remove.type = "button";
  remove.addEventListener("click", () => field.remove());
  field.append(labeled("할 일", title), labeled("요일 (안 고르면 매일)", days), labeled("시각 (선택)", at),
    labeled("관련 수업 (선택, 그 수업이 쉬는 주차에는 알리지 않아요)", course), remove);
  $("routine-rows").append(field);
}

function clearTimetableEditor() {
  const form = $("timetable");
  delete form.dataset.loaded;
  form.reset();
  $("timetable-rows").replaceChildren();
  $("routine-rows").replaceChildren();
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
    const { start, last, classes, routines } = await api("/api/timetable");
    if (form.dataset.loaded !== ticket) return;
    $("timetable-start").value = start;
    $("timetable-last").value = last ?? "";
    classes.forEach(addClassRow);
    routines.forEach(addRoutineRow);
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
  $("routine-add").addEventListener("click", () => {
    if ($("routine-rows").children.length >= 30) return;
    addRoutineRow();
    $("routine-rows").lastElementChild.querySelector('[name="title"]').focus();
  });
  $("timetable").addEventListener("submit", async event => {
    event.preventDefault();
    const status = $("timetable-status");
    const classes = [...$("timetable-rows").children].map(field => {
      const value = name => field.querySelector(`[name="${name}"]`).value;
      const row = { kind: value("kind"), title: value("title"), room: value("room"), off_weeks: weekList(value("off_weeks")) };
      if (row.kind !== "online") {
        Object.assign(row, { day: Number(value("day")), date: value("date"), start: value("start"), end: value("end") });
      }
      return row;
    });
    const routines = [...$("routine-rows").children].map(field => ({
      title: field.querySelector('[name="title"]').value,
      days: [...field.querySelectorAll('[name="days"]:checked')].map(box => Number(box.value)),
      time: field.querySelector('[name="time"]').value,
      course: field.querySelector('[name="course"]').value,
    }));
    setTimetableBusy(true);
    try {
      await api("/api/timetable", { start: $("timetable-start").value, last: $("timetable-last").value, classes, routines });
      status.textContent = `${Object.entries(kinds).map(([kind, label]) => `${label} ${ofKind(classes, kind).length}개`)
        .join(", ")}, 일상 규칙 ${routines.length}개를 저장했어요.`;
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
      // Windows OCR reads small labels better when enlarged (server limit 2200px). A second pass keeps only
      // white pixels so white labels on colored blocks stand out.
      const ocrScale = Math.min(2, 2200 / Math.max(preview.width, preview.height));
      async function readPhoto(whiteOnly) {
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(preview.width * ocrScale);
        canvas.height = Math.round(preview.height * ocrScale);
        const context = canvas.getContext("2d");
        context.imageSmoothingQuality = "high";
        context.drawImage(preview, 0, 0, canvas.width, canvas.height);
        if (whiteOnly) {
          const image = context.getImageData(0, 0, canvas.width, canvas.height);
          const data = image.data;
          for (let i = 0; i < data.length; i += 4) {
            data[i] = data[i + 1] = data[i + 2] = Math.min(data[i], data[i + 1], data[i + 2]) > 170 ? 0 : 255;
          }
          context.putImageData(image, 0, 0);
        }
        const png = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
        if (!png || png.size > 4 * 1024 * 1024) throw new Error("시간표 부분만 잘라서 다시 올려 주세요.");
        const result = await api("/api/timetable/photo", png);
        return { text: result.text, words: result.words.map(word =>
          ({ ...word, x: word.x / ocrScale, y: word.y / ocrScale, w: word.w / ocrScale, h: word.h / ocrScale })) };
      }
      const result = await readPhoto(false);
      if ($("timetable").dataset.loaded !== ticket) return;
      const blocks = await readPhoto(true);
      if ($("timetable").dataset.loaded !== ticket) return;
      recognized.querySelector("p").textContent = result.text;
      recognized.hidden = !result.text;
      const candidates = timetableCandidates(preview, result.words, blocks.words);
      if (candidates.length) {
        // A photo only shows the weekly grid, so keep dated rows (work rosters) and online classes.
        for (const field of [...$("timetable-rows").children]) {
          if (!field.querySelector('[name="date"]').value && field.querySelector('[name="kind"]').value !== "online") field.remove();
        }
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
