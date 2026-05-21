import json
import re
from groq import AsyncGroq
from config import GROQ_API_KEY, ASSESSMENT_MODEL
from database import get_messages, get_session, save_assessment, complete_session
from prompts import ASSESSMENT_PROMPT

client = AsyncGroq(api_key=GROQ_API_KEY)

# Messages that are system artifacts — not real candidate answers
_NOISE_PATTERNS = re.compile(
    r"^\[(Candidate|System).*\]$",
    re.IGNORECASE,
)

# Messages that are repeat requests — not substantive answers
_REPEAT_PATTERNS = re.compile(
    r"^(can you repeat|repeat (the |your )?question|say that again|"
    r"could you repeat|what did you (say|ask)|pardon|come again)",
    re.IGNORECASE,
)


def _clean_transcript(messages: list[dict]) -> str:
    """
    Convert DB messages into a clean, readable transcript for the assessment LLM.

    Filters:
    - Removes early-end markers and other system artifact messages
    - Removes pure repeat requests (no substantive content)
    - Strips leading/trailing whitespace from each message
    - Labels correctly: Sarah / Candidate
    """
    lines = []
    for msg in messages:
        content = msg["content"].strip()
        role = msg["role"]

        # Skip system artifacts
        if _NOISE_PATTERNS.match(content):
            continue

        # Skip repeat requests from candidate — not informative for assessment
        if role == "candidate" and _REPEAT_PATTERNS.match(content):
            continue

        # Skip empty messages
        if not content:
            continue

        label = "Sarah (Interviewer)" if role == "interviewer" else "Candidate"
        lines.append(f"{label}: {content}")

    return "\n\n".join(lines)


async def generate_assessment(session_id: str) -> dict:
    """
    Generate the structured assessment report for a completed session.
    Sends the full cleaned transcript to the assessment LLM.
    """
    # 1. Fetch session + all messages from DB
    session = await get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")

    messages = await get_messages(session_id)

    if not messages:
        raise ValueError(f"No messages found for session {session_id}.")

    # 2. Clean transcript — removes noise, labels correctly
    transcript = _clean_transcript(messages)
    candidate_name = session["candidate_name"]

    # --- SUBSTANCE CHECK ---
    # Count how many lines in the transcript are from the 'Candidate'
    substantive_candidate_lines = [line for line in transcript.split('\n') if line.startswith('Candidate:')]
    
    if len(substantive_candidate_lines) == 0:
        print(f"[Assessment] Session {session_id[:8]}... | ZERO substantive candidate data. Returning automatic fail.")
        
        report = {
            "candidate_name": candidate_name,
            "session_id": session_id,
            "recommendation": "Do not move forward",
            "summary": "This interview contains zero substantive responses from the candidate. The session either ended prematurely or was left entirely blank. No evaluation possible.",
            "dimensions": {
                "communication_clarity": {"score": 0, "justification": "No data available.", "quote": "—"},
                "warmth_and_patience":   {"score": 0, "justification": "No data available.", "quote": "—"},
                "ability_to_simplify":   {"score": 0, "justification": "No data available.", "quote": "—"},
                "english_fluency":       {"score": 0, "justification": "No data available.", "quote": "—"},
                "candidate_fit":         {"score": 0, "justification": "No data available.", "quote": "—"},
            },
            "overall_score": 0.0,
        }
        await save_assessment(session_id, json.dumps(report))
        await complete_session(session_id)
        return report

    # Log transcript length for debugging
    word_count = len(transcript.split())
    print(f"[Assessment] Session {session_id[:8]}... | {len(messages)} raw messages → {word_count} words in cleaned transcript")

    # 3. Build assessment prompt with full transcript
    prompt = ASSESSMENT_PROMPT.format(
        candidate_name=candidate_name,
        session_id=session_id,
        transcript=transcript,
    )

    # 4. Call assessment LLM
    #    - System message sets the evaluator role
    #    - Low temperature for consistent structured JSON output
    response = await client.chat.completions.create(
        model=ASSESSMENT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert educator evaluator. "
                    "You always respond with valid JSON only. No extra text, no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1800,
        temperature=0.2,  # Very low — we want deterministic structured output
    )

    raw = response.choices[0].message.content.strip()

    # 5. Robust JSON extraction
    report = _extract_json(raw, candidate_name, session_id)

    # 6. Save to database
    await save_assessment(session_id, json.dumps(report))
    await complete_session(session_id)

    return report


def _extract_json(raw: str, candidate_name: str, session_id: str) -> dict:
    """
    Robustly extract JSON from LLM output.
    Handles: clean JSON, ```json blocks, ```  blocks, text before/after JSON.
    Never crashes — returns a fallback report if all parsing fails.
    """
    # Strategy 1: Direct parse (ideal case)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences
    fence_stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    fence_stripped = re.sub(r"\s*```$", "", fence_stripped, flags=re.MULTILINE).strip()
    try:
        return json.loads(fence_stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 3: Find the first { ... } block via regex
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 4: Fallback — return a minimal valid report so the UI doesn't crash
    print(f"[Assessment] WARNING: Could not parse JSON for {session_id}. Raw output:\n{raw[:500]}")
    return {
        "candidate_name": candidate_name,
        "session_id": session_id,
        "recommendation": "Consider with reservations",
        "summary": "Assessment could not be fully generated. Please review the transcript manually.",
        "dimensions": {
            "communication_clarity": {"score": 5, "justification": "Unable to parse.", "quote": "—"},
            "warmth_and_patience":   {"score": 5, "justification": "Unable to parse.", "quote": "—"},
            "ability_to_simplify":   {"score": 5, "justification": "Unable to parse.", "quote": "—"},
            "english_fluency":       {"score": 5, "justification": "Unable to parse.", "quote": "—"},
            "candidate_fit":         {"score": 5, "justification": "Unable to parse.", "quote": "—"},
        },
        "overall_score": 5.0,
    }
