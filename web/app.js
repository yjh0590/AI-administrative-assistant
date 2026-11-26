const $ = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("ko-KR", { dateStyle: "full", timeZone: "Asia/Seoul" });
const timeFormat = new Intl.DateTimeFormat("ko-KR", { hour: "numeric", minute: "numeric", timeZone: "Asia/Seoul" });
const shortDateFormat = new Intl.DateTimeFormat("ko-KR", { month: "numeric", day: "numeric", weekday: "short", timeZone: "Asia/Seoul" });
const clockFormat = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Seoul" });
const kaiyonPortraits = [
  { src: "/kaiyon-woman.webp", alt: "초승달 장식의 여성형 카이온" },
  { src: "/kaiyon-man.webp", alt: "각진 갑옷의 남성형 카이온" },
];
const sourceLabels = {
  agenda: ["네이버 캘린더", "오늘 등록된 일정이 없어요."],
  lms: ["LMS 일정", "3일 안에 마감되거나 지금 수강 중인 LMS 일정이 없어요."],
  news: ["관심 뉴스", "조건에 맞는 최근 기사가 없어요."],
  bookings: ["콕콕 페이지 확인", "표시할 예약이 없어요."],
};
const featureTitles = {
  briefing: "오늘의 브리핑",
  school: "학교 시간표",
  life: "생활 캘린더",
  agenda: "네이버 일정",
  lms: "LMS 일정",
  news: "관심 뉴스",
  bookings: "콕콕 예약",
  settings: "알림 설정",
};
const canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
let digest;
let schoolToday;
let schoolRoutines = [];
let schoolWeek = null;
let lifeToday = [];
let speaking;
let poll;
let toastTimer;
let serviceWorker;
let device;
let renderedContent;
let briefingBusy = false;
let briefingCompleted = false;
let completionTimer;

function choosePortrait() {
  const image = $("kaiyon-portrait");
  const portrait = kaiyonPortraits[Math.floor(Math.random() * kaiyonPortraits.length)];
  image.alt = portrait.alt;
  image.src = portrait.src;
  image.hidden = false;
}

function isStandalone() {
  return navigator.standalone || matchMedia("(display-mode: standalone)").matches;
}

function updateClock() {
  const clock = $("clock");
  const time = clockFormat.format(new Date());
  if (clock.dateTime === time) return;
  clock.dateTime = time;
  clock.textContent = time;
}

function connectionState(online) {
  $("connection").hidden = false;
  $("connection").dataset.online = String(online);
  $("connection-label").textContent = online ? "서버 연결됨" : "서버 연결 끊김";
}

function renderKaiyonActivity() {
  const display = $("kaiyon-display");
  if (speaking) display.dataset.state = "speaking";
  else if (briefingBusy) display.dataset.state = "working";
  else display.dataset.state = briefingCompleted ? "ready" : "idle";
}

function setBriefingActivity(busy, completed = false) {
  briefingBusy = busy;
  if (busy || completed) {
    clearTimeout(completionTimer);
    briefingCompleted = completed;
  }
  if (completed) {
    completionTimer = setTimeout(() => {
      briefingCompleted = false;
      renderKaiyonActivity();
    }, 1800);
  }
  renderKaiyonActivity();
}

function message(content, keep = false) {
  clearTimeout(toastTimer);
  $("status").textContent = content;
  $("status").hidden = !content;
  if (content && !keep) toastTimer = setTimeout(() => { $("status").hidden = true; }, 5500);
}

async function api(path, data) {
  const photo = data instanceof Blob;
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST", headers: { "Content-Type": photo ? data.type : "application/json" },
    body: photo ? data : JSON.stringify(data),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    if (response.status === 401) showLogin();
    throw new Error(result.error ?? "요청을 처리하지 못했어요. 다시 시도해 주세요.");
  }
  return response.json();
}

function showLogin() {
  clearTimeout(poll);
  clearTimeout(completionTimer);
  if (canSpeak) speechSynthesis.cancel();
  finishSpeaking();
  digest = null;
  schoolToday = null;
  schoolRoutines = [];
  schoolWeek = null;
  clearTimetableEditor();
  clearLifeEditor();
  lifeToday = [];
  briefingCompleted = false;
  setBriefingActivity(false);
  renderedContent = null;
  $("briefing").replaceChildren();
  $("dashboard").hidden = true;
  $("connection").hidden = true;
  $("login").hidden = false;
}

function node(tag, content, className) {
  const item = document.createElement(tag);
  if (content) item.textContent = content;
  if (className) item.className = className;
  return item;
}

function eventLabel(item, date) {
  if (item.all_day) return "종일";
  const from = item.start.startsWith(date) ? timeFormat.format(new Date(item.start)) : "이전부터";
  if (item.start === item.end) return from;
  const to = item.end.startsWith(date) ? timeFormat.format(new Date(item.end)) : "다음 날까지";
  return `${from} ~ ${to}`;
}

const lmsWhen = value => `${shortDateFormat.format(new Date(value))} ${timeFormat.format(new Date(value))}`;
// Due dates carry one moment; lecture periods carry an open window.
const lmsLabel = item => [item.course, item.kind === "due" ? `마감 ${lmsWhen(item.end)}` : `수강 기간 ~ ${lmsWhen(item.end)}`]
  .filter(Boolean).join(" · ");

function sourceNotice(kind, content) {
  const [label, empty] = sourceLabels[kind];
  if (content.status === "unconfigured") return `${label} 연결이 필요해요.`;
  if (content.status === "unavailable") return `${label} 정보를 가져오지 못했어요.`;
  if (content.status === "partial") return `${label}의 일부 항목을 확인하지 못했어요.`;
  return content.items.length ? "" : empty;
}

function menuStatus(kind) {
  const content = digest?.[kind];
  if (!content) return "브리핑 확인 대기";
  if (content.status === "unconfigured") return "연결 필요";
  if (content.status === "unavailable") return "확인 실패";
  const units = { agenda: "일정", lms: "일정", news: "기사", bookings: "확인 중인 페이지" };
  const count = `${units[kind]} ${content.items.length}건`;
  return content.status === "partial" ? `${count} · 일부 확인` : count;
}

function card(kind, includeHeading) {
  const content = digest[kind];
  const section = node("section", null, "card");
  if (includeHeading) section.append(node("h2", sourceLabels[kind][0]));
  const notice = sourceNotice(kind, content);
  if (notice) section.append(node("p", notice, "muted"));
  const list = node("ul");
  for (const item of content.items) {
    const row = node("li");
    if (item.url) {
      const link = node("a", item.title);
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      row.append(link);
    } else row.append(node("strong", item.title));
    if (kind === "agenda") row.append(node("span", eventLabel(item, digest.date), "detail"));
    if (kind === "lms") row.append(node("span", lmsLabel(item), "detail"));
    if (kind === "news") {
      if (item.summary) row.append(node("p", item.summary));
      row.append(node("span", item.source, "detail"));
    }
    if (kind === "bookings") {
      const checked = item.checked ? ` · 확인 ${dateFormat.format(new Date(item.checked))} ${timeFormat.format(new Date(item.checked))}` : "";
      row.append(node("span", item.status + checked, "detail"));
    }
    list.append(row);
  }
  if (list.childElementCount) section.append(list);
  return section;
}

function renderView(navigated = false) {
  if ($("dashboard").hidden) return;
  const route = location.hash.slice(1);
  const feature = Object.hasOwn(featureTitles, route) ? route : null;
  const settings = feature === "settings";
  const school = feature === "school";
  const life = feature === "life";
  const fullBriefing = feature === "briefing";
  if (!feature && !$("kaiyon-portrait").hasAttribute("src")) choosePortrait();
  $("menu").hidden = Boolean(feature);
  $("feature").hidden = !feature;
  $("settings").hidden = !settings;
  $("briefing-tools").hidden = !feature || settings || school || life;
  $("briefing").hidden = !feature || settings;
  $("timetable").hidden = !school;
  if (school) loadTimetableEditor();
  $("life").hidden = !life;
  if (life) loadLifeEditor();
  const agendaSetup = $("agenda-setup");
  if (feature === "agenda" && (navigated || agendaSetup.hidden)) {
    agendaSetup.open = !digest || digest.agenda.status === "unconfigured";
  }
  agendaSetup.hidden = feature !== "agenda";
  $("listen").hidden = !fullBriefing;
  $("feature-title").textContent = feature ? featureTitles[feature] : "";

  if (feature && !fullBriefing && speaking) {
    speechSynthesis.cancel();
    finishSpeaking();
  }
  if (feature && !settings) {
    const contentKey = `${feature}:${digest?.generated ?? ""}:${JSON.stringify([schoolToday, schoolRoutines, schoolWeek, lifeToday])}`;
    if (renderedContent !== contentKey) {
      // Briefings saved before a source existed lack its key, so only render the ones present.
      const sections = (fullBriefing ? Object.keys(sourceLabels) : [feature]).filter(kind => digest?.[kind]);
      const cards = school || life ? [] : sections.length ? sections.map(kind => card(kind, fullBriefing)) : [
        node("p", "‘지금 확인’을 누르면 오늘 정보를 가져와요.", "card muted"),
      ];
      if (life || (fullBriefing && lifeToday.length)) cards.unshift(lifeCard());
      if (school || (fullBriefing && schoolToday)) cards.unshift(schoolCard());
      $("briefing").replaceChildren(...cards);
      renderedContent = contentKey;
    }
  }
  if (navigated) {
    $(feature ? "feature-title" : "menu-title").focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
}

async function load() {
  clearTimeout(poll);
  const result = await api("/api/briefing");
  const completed = briefingBusy && !result.busy && !result.failed &&
    result.briefing?.generated && result.briefing.generated !== digest?.generated;
  digest = result.briefing;
  schoolToday = result.school;
  schoolRoutines = result.routines ?? [];
  schoolWeek = result.week ?? null;
  lifeToday = result.life ?? [];
  setBriefingActivity(result.busy, Boolean(completed));
  $("login").hidden = true;
  $("dashboard").hidden = false;
  connectionState(true);
  $("today").textContent = dateFormat.format(new Date(`${result.date}T00:00:00+09:00`));
  const updated = digest ? ` · ${timeFormat.format(new Date(digest.generated))} 기준` : "";
  $("schedule").textContent = `매일 ${result.schedule} 브리핑${updated}`;
  $("menu-schedule").textContent = result.busy ? "브리핑을 만드는 중" : `매일 ${result.schedule} 브리핑`;
  const greeting = $("kaiyon-greeting");
  if (result.busy) greeting.textContent = "주인님, 지금 자료를 확인 중입니다.";
  else if (digest || schoolToday) greeting.textContent = "주인님, 오늘 브리핑을 준비했습니다.";
  else greeting.textContent = "주인님, 오늘 브리핑을 준비할까요?";
  for (const kind of Object.keys(sourceLabels)) $(`${kind}-state`).textContent = menuStatus(kind);
  const work = ofKind(schoolToday, "work").length;
  $("school-state").textContent = schoolToday
    ? `오늘 수업 ${ofKind(schoolToday, "class").length}개${work ? ` · 근로 ${work}건` : ""}` : "시간표 등록";
  $("life-state").textContent = plannedLife().length ? `오늘 할 일 ${plannedLife().length}개` : "오늘은 매일 습관만";
  $("refresh").disabled = result.busy;
  $("refresh").textContent = result.busy ? "확인 중…" : "지금 확인";
  for (const id of ["listen", "listen-quick"]) $(id).disabled = !canSpeak || !(digest || schoolToday || lifeToday.length || speaking);
  renderView();
  if (result.failed) message("브리핑을 만들지 못했어요. 잠시 후 다시 확인해 주세요.");
  const interval = result.busy ? 1200 : 30_000;
  poll = setTimeout(pollBriefing, interval);
}

function pollBriefing() {
  load().catch(error => {
    if ($("dashboard").hidden) return;
    connectionState(false);
    message(error.message);
    poll = setTimeout(pollBriefing, 30_000);
  });
}

function spokenText(content) {
  const agenda = content?.agenda.items ?? [];
  const parts = ["주인님, 오늘의 브리핑입니다."];
  if (schoolToday) {
    if (schoolWeek) parts.push(`오늘은 ${schoolWeek}주차입니다.`);
    const lessons = ofKind(schoolToday, "class");
    const work = ofKind(schoolToday, "work");
    if (lessons.length) {
      const first = lessons[0];
      const place = first.room ? ` 강의실은 ${first.room}입니다.` : "";
      parts.push(`오늘 수업은 ${lessons.length}개입니다. 첫 수업은 ${timeFormat.format(new Date(first.start))} ${first.title}입니다.${place}`);
    } else parts.push("오늘 등록된 수업은 없습니다.");
    if (work.length) {
      parts.push(`근로는 ${work.length}건이고, ${work.map(item =>
        `${timeFormat.format(new Date(item.start))}부터 ${timeFormat.format(new Date(item.end))}까지 ${item.title}`).join(", ")}입니다.`);
    }
    if (schoolRoutines.length) {
      parts.push(`오늘 할 일은 ${schoolRoutines.map(item => item.time ? `${item.time}에 ${item.title}` : item.title).join(", ")}입니다.`);
    }
  }
  for (const category of new Set(plannedLife().map(item => item.category))) {
    parts.push(`오늘 ${category} 일정은 ${plannedLife().filter(item => item.category === category)
      .map(item => item.title).join(", ")}입니다.`);
  }
  if (agenda.length) {
    const first = agenda.find(item => !item.all_day) ?? agenda[0];
    const firstTime = first.start.startsWith(content.date) ? timeFormat.format(new Date(first.start)) : "이전부터 이어지는";
    const firstEvent = first.all_day ? `종일 일정인 ${first.title}` : `${firstTime} ${first.title}`;
    parts.push(`오늘 일정은 ${agenda.length}건입니다. 첫 일정은 ${firstEvent}입니다.`);
  }
  const lms = content?.lms?.items ?? [];
  const due = lms.filter(item => item.kind === "due");
  // Mention lecture periods only when they close within two days.
  const closing = lms.filter(item => item.kind === "period" && new Date(item.end) - Date.now() < 2 * 864e5);
  if (due.length) parts.push(`LMS 마감은 ${due.map(item => `${item.course} ${item.title}, ${lmsWhen(item.end)}`).join(", ")}입니다.`);
  if (closing.length) parts.push(`수강 기간이 곧 끝나는 온라인 강의는 ${closing.map(item => `${item.course} ${item.title}`).join(", ")}입니다.`);
  const headlines = content?.news.items.slice(0, 3) ?? [];
  if (headlines.length) parts.push("관심 뉴스 제목입니다.", ...headlines.map(item => `${item.title}.`));
  for (const key of ["agenda", "news"]) {
    if (!content) break;
    const notice = sourceNotice(key, content[key]);
    if (notice && content[key].status !== "unconfigured") parts.push(notice);
  }
  if (parts.length === 1) parts.push("캘린더나 뉴스 소스를 연결하면 브리핑할 내용을 가져옵니다.");
  return parts.join(" ");
}

function toggleSpeech() {
  if (speaking) {
    speechSynthesis.cancel();
    finishSpeaking();
    return;
  }
  if (!digest && !schoolToday && !lifeToday.length) return;
  const utterance = new SpeechSynthesisUtterance(spokenText(digest));
  utterance.lang = "ko-KR";
  const voice = speechSynthesis.getVoices().find(option => option.lang.toLowerCase().startsWith("ko"));
  if (voice) utterance.voice = voice;
  utterance.onend = () => { if (speaking === utterance) finishSpeaking(); };
  utterance.onerror = event => {
    if (speaking !== utterance) return;
    finishSpeaking();
    if (!["canceled", "interrupted"].includes(event.error)) message("음성을 재생하지 못했어요. 기기의 한국어 음성 설정을 확인해 주세요.");
  };
  speaking = utterance;
  updateSpeechControls();
  speechSynthesis.speak(utterance);
}

function updateSpeechControls() {
  for (const id of ["listen", "listen-quick"]) {
    $(id).textContent = speaking ? "듣기 중지" : "브리핑 듣기";
  }
  renderKaiyonActivity();
}

function finishSpeaking() {
  speaking = null;
  updateSpeechControls();
}

$("listen").addEventListener("click", toggleSpeech);
$("listen-quick").addEventListener("click", toggleSpeech);

function showPush() {
  $("push").disabled = !serviceWorker;
  $("push").textContent = device ? "휴대폰 알림 끄기" : "휴대폰 알림 켜기";
  $("push-test").disabled = !device;
  $("settings-state").textContent = device ? "이 기기에서 받는 중" : "이 기기 알림 꺼짐";
}

async function startPush() {
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
  if (ios && !isStandalone()) {
    $("push-help").hidden = false;
    $("push-help").textContent = "Safari 공유 메뉴에서 ‘홈 화면에 추가’를 선택한 뒤, 홈 화면의 카이온 아이콘을 열어 알림을 켜세요.";
    return;
  }
  if (!(window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window)) {
    $("push-help").hidden = false;
    $("push-help").textContent = "HTTPS로 접속해 주세요. 아이폰은 Safari에서 홈 화면에 추가한 뒤 실행해야 해요.";
    return;
  }
  try {
    await navigator.serviceWorker.register("/sw.js");
    serviceWorker = await navigator.serviceWorker.ready;
    device = await serviceWorker.pushManager.getSubscription();
    showPush();
  } catch {
    message("이 브라우저에서 알림을 준비하지 못했어요.");
  }
}

$("push").addEventListener("click", async () => {
  $("push").disabled = true;
  try {
    if (device) {
      await api("/api/push/unsubscribe", { endpoint: device.endpoint });
      await device.unsubscribe();
      device = null;
      message("이 기기에서 알림을 껐어요.");
    } else {
      if (await Notification.requestPermission() !== "granted") throw new Error("브라우저에서 알림을 허용해 주세요.");
      const { key } = await api("/api/push/key");
      const binary = key.replace(/-/g, "+").replace(/_/g, "/");
      const raw = atob(binary.padEnd(Math.ceil(binary.length / 4) * 4, "="));
      const newDevice = await serviceWorker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, c => c.charCodeAt(0)) });
      try {
        await api("/api/push/subscribe", newDevice.toJSON());
      } catch (error) {
        await newDevice.unsubscribe();
        throw error;
      }
      device = newDevice;
      message("이 기기에 아침 브리핑 알림을 등록했어요.");
    }
  } catch (error) {
    message(error.message);
  } finally {
    showPush();
  }
});

$("push-test").addEventListener("click", async () => {
  try {
    await api("/api/push/test", { endpoint: device.endpoint });
    message("테스트 알림을 보냈어요.");
  } catch (error) { message(error.message); }
});

$("refresh").addEventListener("click", async () => {
  $("refresh").disabled = true;
  setBriefingActivity(true);
  try {
    await api("/api/briefing/refresh", {});
    await load();
  } catch (error) {
    $("refresh").disabled = false;
    setBriefingActivity(false);
    message(error.message);
  }
});

$("logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", {});
    history.replaceState(null, "", location.pathname);
    showLogin();
  }
  catch (error) { message(error.message); }
});

$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const input = $("code");
  try {
    await api("/api/session", { code: input.value.trim() });
    input.value = "";
    message("");
    await load();
  } catch (error) { message(error.message); }
});

window.addEventListener("hashchange", () => renderView(true));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && isStandalone() && !$("dashboard").hidden) choosePortrait();
});
updateClock();
initializeTimetable();
initializeLife();
setInterval(updateClock, 1000);
load().catch(error => { if ($("login").hidden) message(error.message); });
startPush();
