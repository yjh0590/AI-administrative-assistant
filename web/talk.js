// Talk to Kaiyon: speak or type a question, the server answers from today's data, Kaiyon reads it aloud.
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let talkState = null;
let talkHistory = [];
let recognizer = null;

function setTalkState(state) {
  talkState = state;
  renderKaiyonActivity();
  $("talk-mic").textContent = state === "listening" ? "듣는 중… (눌러서 멈춤)" : "말하기";
}

function addBubble(text, who) {
  const bubble = node("p", text, `talk-bubble ${who}`);
  $("talk-log").append(bubble);
  $("talk-log").hidden = false;
  bubble.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function speakReply(text) {
  if (!canSpeak) return;
  speechSynthesis.cancel();
  const utterance = makeUtterance(text);
  utterance.onend = utterance.onerror = () => { if (speaking === utterance) finishSpeaking(); };
  speaking = utterance;
  updateSpeechControls();
  speechSynthesis.speak(utterance);
}

// iOS only lets a page speak after a tap, so an empty utterance during the tap unlocks the later reply.
function unlockSpeech() {
  if (canSpeak && !speaking) speechSynthesis.speak(new SpeechSynthesisUtterance(""));
}

async function askKaiyon(text) {
  const question = text.trim().slice(0, 500);
  if (!question || talkState === "thinking") return;
  addBubble(question, "me");
  talkHistory = [...talkHistory, { role: "user", content: question }].slice(-10);
  setTalkState("thinking");
  try {
    const { reply } = await api("/api/chat", { messages: talkHistory });
    talkHistory = [...talkHistory, { role: "assistant", content: reply }].slice(-10);
    addBubble(reply, "kaiyon");
    setTalkState(null);
    speakReply(reply);
  } catch (error) {
    // Drop the unanswered question so the next try does not send it twice.
    talkHistory = talkHistory.slice(0, -1);
    addBubble(error.message, "notice");
    setTalkState(null);
  }
}

function listen() {
  unlockSpeech();
  if (recognizer) {
    recognizer.stop();
    return;
  }
  if (!Recognition) {
    $("talk-input").focus();
    return;
  }
  if (speaking) {
    speechSynthesis.cancel();
    finishSpeaking();
  }
  recognizer = new Recognition();
  recognizer.lang = "ko-KR";
  recognizer.interimResults = true;
  let heard = "";
  recognizer.onresult = event => {
    heard = [...event.results].map(result => result[0].transcript).join("");
    $("talk-input").value = heard;
  };
  recognizer.onerror = event => {
    if (event.error === "not-allowed") addBubble("마이크 권한이 필요해요. 설정에서 마이크를 허용하거나 글자로 물어봐 주세요.", "notice");
  };
  recognizer.onend = () => {
    recognizer = null;
    setTalkState(null);
    $("talk-input").value = "";
    if (heard) askKaiyon(heard);
  };
  setTalkState("listening");
  recognizer.start();
}

function poke() {
  // A short bounce so the tap feels answered even before the mic starts.
  const display = $("kaiyon-display");
  display.classList.remove("poked");
  void display.offsetWidth;
  display.classList.add("poked");
  listen();
}

function initializeTalk() {
  $("talk-mic").hidden = !Recognition;
  $("talk-mic").addEventListener("click", listen);
  $("kaiyon-talk").addEventListener("click", poke);
  $("talk-form").addEventListener("submit", event => {
    event.preventDefault();
    unlockSpeech();
    const input = $("talk-input");
    askKaiyon(input.value);
    input.value = "";
  });
}
