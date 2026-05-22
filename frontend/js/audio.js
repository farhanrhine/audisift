export const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
export const hasSpeechAPI = !!SpeechRecognition;
export const synth = window.speechSynthesis;

// To prevent Chrome Garbage Collection of SpeechSynthesisUtterance instances before completion
window.speechUtterances = [];

export function speakText(text, onStart, onEnd) {
  if (!synth) return;
  synth.cancel();
  
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.0;
  utter.pitch = 1.05;
  utter.volume = 1;

  const voices = synth.getVoices();
  const preferred = voices.find(v =>
    v.name.includes('Samantha') || v.name.includes('Google UK English Female') ||
    v.name.includes('Microsoft Zira') || v.name.includes('Female')
  ) || voices.find(v => v.lang.startsWith('en'));
  
  if (preferred) utter.voice = preferred;

  utter.onstart = onStart;
  utter.onend = () => {
    // Remove from global array to allow GC
    window.speechUtterances = window.speechUtterances.filter(u => u !== utter);
    if (onEnd) onEnd();
  };
  utter.onerror = (e) => {
    console.error('Speech error:', e);
    window.speechUtterances = window.speechUtterances.filter(u => u !== utter);
    if (onEnd) onEnd();
  };

  // CHROME GC BUG FIX: Prevent the utterance from being deleted before it finishes
  window.speechUtterances.push(utter);
  
  synth.speak(utter);
}

// Media recorder logic
let mediaRecorder = null;
let audioChunks = [];
let recognition = null;
let transcribeWebSocket = null;  // Phase 6: WebSocket for streaming transcription

export function isAudioRecording() {
  return mediaRecorder !== null || recognition !== null;
}

export function startRecordingSession(onTranscribeText, onFinalTranscribe, onStopCallback, sessionId) {
  const chunks = [];
  let currentRec = null;

  return new Promise((resolve, reject) => {
    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then(stream => {
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : MediaRecorder.isTypeSupported('audio/webm')
            ? 'audio/webm'
            : 'audio/ogg;codecs=opus';

        mediaRecorder = new MediaRecorder(stream, { mimeType });
        mediaRecorder.ondataavailable = e => {
          if (e.data && e.data.size > 0) chunks.push(e.data);
          
          // Phase 6: Stream chunk to WebSocket if connected
          if (transcribeWebSocket && transcribeWebSocket.readyState === WebSocket.OPEN) {
            e.data.arrayBuffer().then(buffer => {
              transcribeWebSocket.send(new Uint8Array(buffer));
            });
          }
        };
        
        mediaRecorder.onstop = () => {
            const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
            stream.getTracks().forEach(t => t.stop());
            
            // Phase 6: Signal end of audio to WebSocket
            if (transcribeWebSocket && transcribeWebSocket.readyState === WebSocket.OPEN) {
              transcribeWebSocket.send(new TextEncoder().encode('__END__'));
            }
            
            onStopCallback(blob);
            mediaRecorder = null;
        };

        // Phase 6: Open WebSocket connection for real-time transcription
        if (sessionId && window.location.protocol !== 'file:') {
          const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const wsUrl = `${wsProtocol}//${window.location.host}/ws/transcribe/${sessionId}`;
          try {
            transcribeWebSocket = new WebSocket(wsUrl);
            transcribeWebSocket.binaryType = 'arraybuffer';
            
            transcribeWebSocket.onmessage = (event) => {
              try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'interim' && msg.text) {
                  onTranscribeText(msg.text, '');  // interim update
                } else if (msg.type === 'final' && msg.text) {
                  onFinalTranscribe(msg.text);  // final transcription
                }
              } catch(e) {
                console.warn('WebSocket message parse error:', e);
              }
            };
            
            transcribeWebSocket.onerror = (e) => {
              console.warn('WebSocket error:', e);
            };
            
            transcribeWebSocket.onclose = () => {
              console.log('Transcription WebSocket closed');
              transcribeWebSocket = null;
            };
          } catch(e) {
            console.warn('WebSocket connection failed, falling back to Web Speech API:', e);
          }
        }

        mediaRecorder.start(250);
        
        if (hasSpeechAPI) {
          recognition = new SpeechRecognition();
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = 'en-US';

          recognition.onresult = (event) => {
            let finalText = '';
            for (let i = 0; i < event.results.length; i++) {
              if (event.results[i].isFinal) finalText += event.results[i][0].transcript + ' ';
            }
            let interimText = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
              if (!event.results[i].isFinal) interimText += event.results[i][0].transcript;
            }
            onTranscribeText(finalText, interimText);
          };

          recognition.onerror = (e) => {
            if (e.error !== 'no-speech') console.warn('Web Speech error:', e.error);
          };
          
          recognition.onend = () => {
              // Usually handled by orchestrator if recording is active
          };
          recognition.start();
        }
        
        resolve({ mediaRecorder, recognition });
      })
      .catch(err => {
        reject(err);
      });
  });
}

export function stopRecordingSession() {
  if (recognition) {
    try { recognition.stop(); } catch(e) {}
    recognition = null;
  }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
  }
}
