"""
WebSocket handler for real-time audio transcription via Groq Whisper.
Buffers audio chunks and sends periodic transcription updates.
"""
import io
import asyncio
from groq import AsyncGroq

try:
    from backend.config import GROQ_API_KEY, WHISPER_MODEL
except ImportError:
    from config import GROQ_API_KEY, WHISPER_MODEL


class AudioBuffer:
    """Buffers audio chunks and transcribes every N seconds."""
    
    def __init__(self, timeout_sec: float = 2.0):
        self.buffer = io.BytesIO()
        self.timeout_sec = timeout_sec
        self.last_transcribe_time = asyncio.get_event_loop().time()
        self.client = AsyncGroq(api_key=GROQ_API_KEY)
        self.total_size = 0
    
    def add_chunk(self, chunk: bytes):
        """Add audio chunk to buffer."""
        if chunk:
            self.buffer.write(chunk)
            self.total_size += len(chunk)
    
    def should_transcribe(self) -> bool:
        """Check if enough time has passed to transcribe buffer."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self.last_transcribe_time
        return elapsed >= self.timeout_sec and self.total_size > 0
    
    async def transcribe(self) -> str:
        """Transcribe buffered audio and return text."""
        if self.total_size == 0:
            return ""
        
        try:
            audio_bytes = self.buffer.getvalue()
            
            # Create a new buffer for the transcription call
            transcription = await self.client.audio.transcriptions.create(
                file=("audio.webm", audio_bytes),
                model=WHISPER_MODEL,
                response_format="json",
                language="en",  # Explicitly request English
            )
            
            # Reset buffer and timer
            self.buffer = io.BytesIO()
            self.total_size = 0
            self.last_transcribe_time = asyncio.get_event_loop().time()
            
            text = transcription.text or ""
            return text.strip()
        except Exception as e:
            print(f"Transcription error: {e}")
            # Reset anyway to avoid buffer overflow
            self.buffer = io.BytesIO()
            self.total_size = 0
            self.last_transcribe_time = asyncio.get_event_loop().time()
            return ""
    
    def get_final_transcription(self) -> bytes:
        """Get raw audio bytes for final transcription."""
        return self.buffer.getvalue()
    
    def clear(self):
        """Clear buffer."""
        self.buffer = io.BytesIO()
        self.total_size = 0
