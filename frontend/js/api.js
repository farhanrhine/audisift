export const BACKEND_URL = '';
export const API = (path) => `${BACKEND_URL}/api${path}`;

export async function fetchStartSession(name, email, token) {
  const authToken = localStorage.getItem('access_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {})
  };
  const res = await fetch(API('/session/start'), {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({
      candidate_name: name,
      candidate_email: email || null,
      token: token || null
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

export async function fetchTranscribe(blob) {
  const ext = blob.type.includes('ogg') ? 'ogg' : 'webm';
  const formData = new FormData();
  formData.append('file', blob, `answer.${ext}`);

  const res = await fetch(API('/transcribe'), { method: 'POST', body: formData });
  if (!res.ok) throw new Error(`Transcribe HTTP ${res.status}`);
  return await res.json();
}

export async function fetchSendMessage(sessionId, text, timeRemaining) {
  const res = await fetch(API('/session/message'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      session_id: sessionId, 
      candidate_message: text,
      time_remaining: timeRemaining
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

export async function pollForReportResult(sessionId) {
  const res = await fetch(API(`/session/report/${sessionId}`));
  return await res.json();
}
