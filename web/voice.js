// Voice settings for the briefing and talk replies: one voice per Kaiyon portrait. Each device keeps its own choice.
const voicePrefs = { woman: "", man: "", rate: 1, pitch: 1 };
try { Object.assign(voicePrefs, JSON.parse(localStorage.getItem("kaiyon-voice") || "{}")); } catch { /* private mode */ }

const koreanVoices = () => (canSpeak ? speechSynthesis.getVoices().filter(voice => voice.lang.toLowerCase().startsWith("ko")) : []);
// Downloaded high-quality voices sound far less robotic, so they win when nothing was chosen.
const QUALITY = /premium|프리미엄|enhanced|향상|고품질|natural|neural/i;
const qualityFirst = voices => [...voices].sort((a, b) => QUALITY.test(b.name) - QUALITY.test(a.name));
// ponytail: guesses male voices from known names (Microsoft InJoon/Hyunsu/..., Apple Minsu); pick by hand if a device names them differently.
const maleVoice = voice => /injoon|인준|hyunsu|현수|bongjin|봉진|gookmin|국민|minsu|민수/i.test(voice.name);
// The chosen pair on iPhone: Minsu (Premium) for the male Kaiyon, Jian (Premium) for the female one.
const PREFERRED = { man: /minsu|민수/i, woman: /jian|지안/i };

function autoVoice(character, voices) {
  const ranked = qualityFirst(voices);
  return ranked.find(voice => PREFERRED[character].test(voice.name))
    ?? (character === "man" ? ranked.find(maleVoice) : ranked.find(voice => !maleVoice(voice))) ?? ranked[0];
}

// The portrait on screen decides who is speaking.
const currentCharacter = () => ($("kaiyon-portrait").getAttribute("src")?.includes("woman") ? "woman" : "man");

function makeUtterance(text, character = currentCharacter()) {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "ko-KR";
  const voices = koreanVoices();
  const voice = voices.find(option => option.name === voicePrefs[character]) ?? autoVoice(character, voices);
  if (voice) utterance.voice = voice;
  utterance.rate = voicePrefs.rate;
  utterance.pitch = voicePrefs.pitch;
  return utterance;
}

function saveVoice() {
  try { localStorage.setItem("kaiyon-voice", JSON.stringify(voicePrefs)); } catch { /* private mode */ }
}

function fillVoices() {
  const voices = koreanVoices();
  for (const character of ["woman", "man"]) {
    const select = $(`voice-${character}`);
    const auto = autoVoice(character, voices);
    select.replaceChildren(new Option(auto ? `자동 (${auto.name})` : "기기 기본 음성", ""),
      ...voices.map(voice => new Option(voice.name, voice.name)));
    select.value = voices.some(voice => voice.name === voicePrefs[character]) ? voicePrefs[character] : "";
  }
  $("voice-count").textContent = voices.length ? `이 기기의 한국어 음성 ${voices.length}개` : "이 기기에서 한국어 음성을 찾지 못했어요.";
}

function initializeVoice() {
  if (!canSpeak) {
    $("voice-settings").hidden = true;
    return;
  }
  $("voice-rate").value = voicePrefs.rate;
  $("voice-pitch").value = voicePrefs.pitch;
  fillVoices();
  speechSynthesis.addEventListener("voiceschanged", fillVoices);
  for (const character of ["woman", "man"]) {
    $(`voice-${character}`).addEventListener("change", event => { voicePrefs[character] = event.target.value; saveVoice(); });
    $(`voice-test-${character}`).addEventListener("click", () => {
      speechSynthesis.cancel();
      speechSynthesis.speak(makeUtterance(`${callName}, ${character === "woman" ? "여성형" : "남성형"} 카이온입니다. 오늘 첫 수업은 오후 3시 행정법입니다.`, character));
    });
  }
  for (const [id, key] of [["voice-rate", "rate"], ["voice-pitch", "pitch"]]) {
    $(id).addEventListener("input", event => { voicePrefs[key] = Number(event.target.value); saveVoice(); });
  }
  $("voice-reset").addEventListener("click", () => {
    Object.assign(voicePrefs, { woman: "", man: "", rate: 1, pitch: 1 });
    saveVoice();
    $("voice-rate").value = 1;
    $("voice-pitch").value = 1;
    fillVoices();
  });
}
