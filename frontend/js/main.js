import * as API from './api.js';
import * as Audio from './audio.js';
import * as UI from './ui.js';

// --- State ---
let sessionId = null;
let isRecording = false;
let isSpeaking = false;
let isProcessing = false;
let questionCount = 0;
const MAX_QUESTIONS = 8;
let timerInterval = null;
let timerSeconds = 0;
let silenceTimer = null;
let accumulatedTranscript = '';
const MIC_MAX_SECONDS = 60;
const INTERVIEW_TOTAL_SECONDS = 600; // 10-minute interview
let interviewToken = null;

let currentUser = null;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  const urlParams = new URLSearchParams(window.location.search);
  interviewToken = urlParams.get('token');

  // Enforce auth check
  try {
    currentUser = await checkAuth();
    if (currentUser.role === 'candidate') {
      const nameInput = document.getElementById('candidate-name');
      const emailInput = document.getElementById('candidate-email');
      if (nameInput) {
        nameInput.value = currentUser.full_name || '';
        nameInput.disabled = true;
        nameInput.style.opacity = '0.7';
      }
      if (emailInput) {
        emailInput.value = currentUser.email || '';
        emailInput.disabled = true;
        emailInput.style.opacity = '0.7';
      }
    }
  } catch (e) {
    // If not authenticated, proceed as anonymous candidate
    console.log("Not authenticated, proceeding as anonymous candidate.");
  }

  const isSupported = /Chrome|Chromium|Edg/.test(navigator.userAgent);
  if (!isSupported) {
    const warn = document.getElementById('chrome-warning');
    if (warn) warn.style.display = 'block';
  }

  const nameInput = document.getElementById('candidate-name');
  if (nameInput) {
    nameInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') startInterview();
    });
  }

  const emailInput = document.getElementById('candidate-email');
  if (emailInput) {
    emailInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') startInterview();
    });
  }

  if (!Audio.hasSpeechAPI) {
    const textFallback = document.getElementById('text-fallback');
    if (textFallback) textFallback.classList.add('show');
    const micBtn = document.getElementById('mic-btn');
    if (micBtn) micBtn.disabled = true;
    const micLabel = document.getElementById('mic-label');
    if (micLabel) micLabel.textContent = 'Type your answer below';
  }

  // Listen for enter key on input box
  const textInput = document.getElementById('text-input');
  if (textInput) {
    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendTextAnswer();
    });
  }
});

function setProcessing(val) {
  isProcessing = val;
  const micBtn = document.getElementById('mic-btn');
  const textInput = document.getElementById('text-input');
  if (micBtn) micBtn.disabled = val;
  if (textInput) textInput.disabled = val;
  if (val) UI.setStatus('processing', 'Processing…');
}

async function startInterview() {
  const nameInput = document.getElementById('candidate-name');
  const emailInput = document.getElementById('candidate-email');
  
  const name = nameInput.value.trim();
  const email = emailInput ? emailInput.value.trim() : '';

  if (!name) {
    nameInput.focus();
    nameInput.style.borderColor = 'var(--accent)';
    setTimeout(() => nameInput.style.borderColor = '', 1500);
    return;
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!email || !emailRegex.test(email)) {
    if (emailInput) {
      emailInput.focus();
      emailInput.style.borderColor = 'var(--accent)';
      setTimeout(() => emailInput.style.borderColor = '', 1500);
    }
    return;
  }

  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  try {
    const data = await API.fetchStartSession(name, email, interviewToken);
    sessionId = data.session_id;

    document.getElementById('welcome-screen').style.display = 'none';
    document.getElementById('interview-screen').style.display = 'block';
    
    const navProg = document.getElementById('nav-progress');
    const navTimer = document.getElementById('nav-timer');
    if (navProg) navProg.style.display = 'flex';
    if (navTimer) navTimer.style.display = 'block';

    startTimer();
    UI.updateProgress(1, MAX_QUESTIONS);

    await showAriaMessage(data.opening_message, true);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = 'Start Interview →';
    alert('Failed to connect. Please check your connection and try again.');
    console.error(err);
  }
}

async function showAriaMessage(text, enableMicAfter) {
  if (!text || !text.trim()) {
    if (enableMicAfter) {
      setProcessing(false);
      UI.setStatus('idle', 'Ready — your turn');
    }
    return;
  }
  
  const typingWrap = document.getElementById('typing-wrap');
  if (typingWrap) typingWrap.classList.add('show');
  UI.setStatus('processing', 'Thinking…');
  await UI.delay(400);

  if (typingWrap) typingWrap.classList.remove('show');

  const chat = document.getElementById('chat-messages');
  const wrap = document.createElement('div');
  wrap.className = 'message-wrap';
  
  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar aria-av';
  avatar.textContent = 'S';
  
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble aria-msg';
  
  const msgDiv = document.createElement('div');
  const timeDiv = document.createElement('div');
  timeDiv.className = 'msg-time';
  timeDiv.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  
  bubble.appendChild(msgDiv);
  bubble.appendChild(timeDiv);
  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  
  if (typingWrap) chat.insertBefore(wrap, typingWrap);
  else chat.appendChild(wrap);

  UI.setStatus('speaking', 'Speaking…');

  Audio.speakText(text, 
    () => { isSpeaking = true; }, 
    () => { 
      isSpeaking = false; 
      UI.setStatus('idle', 'Ready — your turn');
      if (enableMicAfter) setProcessing(false);
    }
  );

  await UI.typewriter(msgDiv, text, 18);
  chat.scrollTop = chat.scrollHeight;
}

function toggleMic() {
  if (isProcessing || isSpeaking) return;
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

function startRecording() {
  accumulatedTranscript = '';
  isRecording = true;
  UI.setMicRecordingUI(true);
  UI.setStatus('listening', 'Listening…');

  silenceTimer = setTimeout(() => { if (isRecording) stopRecording(); }, MIC_MAX_SECONDS * 1000);

  Audio.startRecordingSession(
    (finalText, interimText) => {
      if (finalText.trim()) accumulatedTranscript = finalText.trim();
      const textInput = document.getElementById('text-input');
      if (textInput) textInput.value = (accumulatedTranscript + ' ' + interimText).trim();
    },
    () => {}, // full transcript handled above
    async (blob) => {
      // Audio completely stopped, transcribe via Whisper
      UI.setMicRecordingUI(false);
      await _transcribeAndSend(blob);
    },
    sessionId  // Phase 6: Pass sessionId for WebSocket transcription
  ).catch(err => {
    console.error('Mic access denied:', err);
    isRecording = false;
    UI.setMicRecordingUI(false);
    UI.setStatus('idle', 'Mic access denied — type your answer');
  });
}

function stopRecording() {
  clearTimeout(silenceTimer);
  isRecording = false;
  Audio.stopRecordingSession();
  
  // If NO whisper blob (e.g. no recorder), directly fallback sending
  if (!Audio.isAudioRecording()) {
    UI.setMicRecordingUI(false);
    const fallback = accumulatedTranscript.trim();
    accumulatedTranscript = '';
    if (fallback) sendAnswer(fallback);
  }
}

function sendTextAnswer() {
  if (isProcessing || isSpeaking) return;
  
  const input = document.getElementById('text-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  // Immediate Lock
  setProcessing(true);

  if (isRecording) {
    clearTimeout(silenceTimer);
    isRecording = false; 
    Audio.stopRecordingSession(); 
    UI.setMicRecordingUI(false);
  }

  accumulatedTranscript = '';
  input.value = '';
  sendAnswer(text);
}

async function _transcribeAndSend(blob) {
  // If we already moved to a manual send lock, ignore this audio stop event
  if (isProcessing || isSpeaking) return; 

  if (!blob || blob.size < 1000) {
    UI.setStatus('idle', 'Ready — your turn');
    return;
  }

  setProcessing(true); // Lock the UI during transcription
  UI.setStatus('processing', 'Transcribing…');
  
  const textInput = document.getElementById('text-input');
  if (textInput) textInput.value = 'Transcribing your answer…';
  
  try {
    const data = await API.fetchTranscribe(blob);
    const text = (data.text || '').trim();
    
    if (text) {
      if (textInput) textInput.value = ''; 
      sendAnswer(text);
    } else {
      throw new Error('Empty transcript from Whisper');
    }
  } catch (err) {
    console.error('Whisper transcription failed:', err);
    const fallback = accumulatedTranscript.trim();
    accumulatedTranscript = '';
    if (textInput) textInput.value = '';

    if (fallback) {
      sendAnswer(fallback);
    } else {
      setProcessing(false);
      UI.setStatus('idle', 'Ready — your turn');
    }
  }
}

async function sendAnswer(text) {
  // We only check sessionId and text here; entry points handle isProcessing
  if (!sessionId || !text || !text.trim()) {
    setProcessing(false);
    return;
  }

  setProcessing(true); 
  UI.addMessage(text, 'candidate');

  try {
    const ctrlCountdown = document.getElementById('ctrl-countdown');
    const timeRemaining = ctrlCountdown ? ctrlCountdown.textContent : '10:00'; // 10-min max
    
    const data = await API.fetchSendMessage(sessionId, text, timeRemaining);
    
    questionCount++;
    UI.updateProgress(questionCount + 1, MAX_QUESTIONS);

    if (data.interview_complete) {
      await showAriaMessage(data.interviewer_response, false);
      setProcessing(true); // Maintain lock during transition
      await UI.delay(2000);
      UI.showGeneratingScreen();
      clearInterval(timerInterval);
      
      if (currentUser && currentUser.role === 'candidate') {
        window.location.href = `thankyou.html?candidate_name=${encodeURIComponent(currentUser.full_name)}`;
      } else {
        pollForReport();
      }
    } else {
      await showAriaMessage(data.interviewer_response, true);
    }
  } catch (err) {
    UI.addErrorMessage('Something went wrong. Please try again.');
    console.error(err);
    setProcessing(false);
    UI.setStatus('idle', 'Ready');
  }
}

function pollForReport() {
  const interval = setInterval(async () => {
    try {
      const data = await API.pollForReportResult(sessionId);
      if (data.status === 'ready') {
        clearInterval(interval);
        window.location.href = `report.html?session_id=${sessionId}`;
      }
    } catch (err) {
      console.error('Poll error:', err);
    }
  }, 3000);
}

function startTimer() {
  timerSeconds = 0;
  timerInterval = setInterval(() => {
    timerSeconds++;
    const em = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
    const es = String(timerSeconds % 60).padStart(2, '0');
    const elapsed = `${em}:${es}`;
    
    const navT = document.getElementById('nav-timer');
    const ctrlT = document.getElementById('ctrl-timer');
    if (navT) navT.textContent = elapsed;
    if (ctrlT) ctrlT.textContent = elapsed;

    const remaining = Math.max(0, INTERVIEW_TOTAL_SECONDS - timerSeconds);
    const rm = String(Math.floor(remaining / 60)).padStart(2, '0');
    const rs = String(remaining % 60).padStart(2, '0');
    const countdown = `${rm}:${rs}`;
    
    const ctrlCountdown = document.getElementById('ctrl-countdown');
    if (ctrlCountdown) {
      ctrlCountdown.textContent = countdown;
      ctrlCountdown.style.color = remaining <= 60 ? 'var(--danger)' : 'var(--ink)';
    }

    const timePct = Math.min((timerSeconds / INTERVIEW_TOTAL_SECONDS) * 100, 100);
    const timeBar = document.getElementById('ctrl-time-bar');
    if (timeBar) timeBar.style.width = `${timePct}%`;

    if (remaining <= 0) {
      clearInterval(timerInterval);
      autoEndInterview();
    }
  }, 1000);
}

function autoEndInterview() {
  if (isRecording) {
    clearTimeout(silenceTimer);
    isRecording = false;
    Audio.stopRecordingSession();
    UI.setMicRecordingUI(false);
  }
  UI.setStatus('idle', 'Time is up!');
  
  if (isProcessing) {
    const waitInterval = setInterval(() => {
      if (!isProcessing) {
        clearInterval(waitInterval);
        sendAnswer('[System: Interview ended automatically due to 10-minute time limit]');
      }
    }, 1000);
  } else {
    sendAnswer('[System: Interview ended automatically due to 10-minute time limit]');
  }
}

function confirmEndInterview() {
  if (isRecording) {
    clearTimeout(silenceTimer);
    isRecording = false;
    Audio.stopRecordingSession();
    UI.setMicRecordingUI(false);
  }
  if (confirm('End the interview early? Your assessment will be generated from answers so far.')) {
    sendAnswer('[Candidate chose to end interview early]');
  }
}

// Global exposure for HTML onclick bindings
window.startInterview = startInterview;
window.toggleMic = toggleMic;
window.stopRecording = stopRecording;
window.sendTextAnswer = sendTextAnswer;
window.confirmEndInterview = confirmEndInterview;
