import json
import re
from groq import AsyncGroq
try:
    from backend.config import GROQ_API_KEY, ASSESSMENT_MODEL
    from backend.database import get_messages, get_session, save_assessment, complete_session
    from backend.prompts import ASSESSMENT_PROMPT, ASSESSMENT_RUBRICS, build_rubric_string
except ImportError:
    from config import GROQ_API_KEY, ASSESSMENT_MODEL
    from database import get_messages, get_session, save_assessment, complete_session
    from prompts import ASSESSMENT_PROMPT, ASSESSMENT_RUBRICS, build_rubric_string

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
    Also counts substantive candidate responses for data quality checks.
    """
    lines = []
    candidate_message_count = 0
    
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
        
        if role == "candidate":
            candidate_message_count += 1

    return "\n\n".join(lines), candidate_message_count


async def generate_assessment(session_id: str) -> dict:
    """
    Generate a structured assessment report with rubric-based scoring and confidence scores.
    Phase 4 enhancements: confidence per dimension, flags for data quality, evidence quotes.
    """
    # 1. Fetch session + all messages from DB
    session = await get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")

    messages = await get_messages(session_id)

    if not messages:
        raise ValueError(f"No messages found for session {session_id}.")

    # 2. Clean transcript with candidate message count
    transcript, candidate_count = _clean_transcript(messages)
    candidate_name = session.candidate_name if hasattr(session, 'candidate_name') else session.get("candidate_name", "Unknown")

    # --- DATA QUALITY CHECK ---
    flags = []
    
    if candidate_count == 0:
        print(f"[Assessment] Session {session_id[:8]}... | ZERO substantive candidate data.")
        flags.append("zero_data_detected")
        report = _create_zero_data_report(candidate_name, session_id)
        await save_assessment(session_id, json.dumps(report))
        await complete_session(session_id)
        return report
    
    if candidate_count < 3:
        flags.append("short_interview")
    
    if candidate_count <= 2:
        flags.append("insufficient_data")

    word_count = len(transcript.split())
    if word_count < 100:
        flags.append("limited_transcript")

    # 3. Build enhanced assessment prompt with rubrics
    rubrics_text = build_rubric_string()
    prompt = ASSESSMENT_PROMPT.format(
        candidate_name=candidate_name,
        session_id=session_id,
        transcript=transcript,
        rubrics=rubrics_text,
    )

    # 4. Call assessment LLM with structured output
    response = await client.chat.completions.create(
        model=ASSESSMENT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert educator evaluator with deep knowledge of teaching excellence. "
                    "You always respond with valid JSON only. No extra text, no markdown fences. "
                    "For each dimension, provide: score (1-10), confidence (high|medium|low), "
                    "justification (2-3 sentences), and evidence_quote (a direct quote from the transcript). "
                    "Add flags array for data quality issues. Calculate overall_score as average of 5 dimensions."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=2500,
        temperature=0.3,  # Low temperature for consistent scoring
    )

    raw = response.choices[0].message.content.strip()

    # 5. Robust JSON extraction and enhancement
    report = _extract_and_enhance_json(raw, candidate_name, session_id, flags, candidate_count)

    # 6. Save to database
    await save_assessment(session_id, json.dumps(report))
    await complete_session(session_id)

    return report




def _create_zero_data_report(candidate_name: str, session_id: str) -> dict:
    """Create a minimal report when candidate provided no substantive data."""
    return {
        "candidate_name": candidate_name,
        "session_id": session_id,
        "recommendation": "Do not move forward",
        "summary": "This interview contains zero substantive responses from the candidate. The session either ended prematurely or was left entirely blank. No evaluation possible.",
        "dimensions": {
            "communication_clarity": {
                "score": 0,
                "confidence": "high",
                "justification": "No data available for assessment.",
                "evidence_quote": "—"
            },
            "warmth_and_patience": {
                "score": 0,
                "confidence": "high",
                "justification": "No data available for assessment.",
                "evidence_quote": "—"
            },
            "ability_to_simplify": {
                "score": 0,
                "confidence": "high",
                "justification": "No data available for assessment.",
                "evidence_quote": "—"
            },
            "english_fluency": {
                "score": 0,
                "confidence": "high",
                "justification": "No data available for assessment.",
                "evidence_quote": "—"
            },
            "candidate_fit": {
                "score": 0,
                "confidence": "high",
                "justification": "No data available for assessment.",
                "evidence_quote": "—"
            },
        },
        "overall_score": 0.0,
        "percentile_rank": None,
        "flags": ["zero_data_detected"],
    }


def _extract_and_enhance_json(raw: str, candidate_name: str, session_id: str, flags: list, candidate_count: int) -> dict:
    """
    Extract JSON from LLM output and add Phase 4 enhancements.
    Adds confidence scores, flags, and validates data quality.
    """
    # Try to parse JSON
    report = None
    
    # Strategy 1: Direct parse
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences
    if not report:
        fence_stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        fence_stripped = re.sub(r"\s*```$", "", fence_stripped, flags=re.MULTILINE).strip()
        try:
            report = json.loads(fence_stripped)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find the first { ... } block
    if not report:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                report = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    # Strategy 4: Fallback
    if not report:
        print(f"[Assessment] WARNING: Could not parse JSON for {session_id}. Raw:\n{raw[:500]}")
        report = _create_fallback_report(candidate_name, session_id)

    # Ensure structure exists
    if "dimensions" not in report:
        report["dimensions"] = {}

    # Add confidence scores if not present
    for dim_key in ["communication_clarity", "warmth_and_patience", "ability_to_simplify", "english_fluency", "candidate_fit"]:
        if dim_key not in report["dimensions"]:
            report["dimensions"][dim_key] = {
                "score": 5,
                "confidence": "medium",
                "justification": "Insufficient data.",
                "evidence_quote": "—"
            }
        else:
            # Ensure all required fields exist
            if "confidence" not in report["dimensions"][dim_key]:
                report["dimensions"][dim_key]["confidence"] = _infer_confidence(report["dimensions"][dim_key].get("score", 5))
            if "evidence_quote" not in report["dimensions"][dim_key]:
                report["dimensions"][dim_key]["evidence_quote"] = "—"

    # Calculate overall score if not present
    if "overall_score" not in report or not report["overall_score"]:
        scores = [
            report["dimensions"].get(k, {}).get("score", 5)
            for k in ["communication_clarity", "warmth_and_patience", "ability_to_simplify", "english_fluency", "candidate_fit"]
        ]
        report["overall_score"] = round(sum(scores) / len(scores), 1)

    # Add flags for data quality
    if "flags" not in report:
        report["flags"] = []
    
    report["flags"].extend(flags)
    
    # If too many low-confidence dimensions, add insufficient_data flag
    low_confidence_count = sum(
        1 for dim in report["dimensions"].values()
        if dim.get("confidence") == "low"
    )
    if low_confidence_count >= 3:
        report["flags"].append("insufficient_data")

    # Add percentile_rank (placeholder, nullable for now)
    if "percentile_rank" not in report:
        report["percentile_rank"] = None

    # Ensure other fields
    report.setdefault("candidate_name", candidate_name)
    report.setdefault("session_id", session_id)
    report.setdefault("recommendation", "Consider with reservations")
    report.setdefault("summary", "Assessment completed. Review dimensions for detailed feedback.")

    return report


def _infer_confidence(score: int) -> str:
    """Infer confidence level based on score clarity."""
    if score in [0, 10]:
        return "high"  # Extreme scores indicate strong evidence
    elif score in [1, 9, 2, 8]:
        return "high"  # Clear patterns
    elif score in [3, 7, 4, 6]:
        return "medium"
    else:
        return "medium"


def _create_fallback_report(candidate_name: str, session_id: str) -> dict:
    """Fallback report when JSON parsing completely fails."""
    return {
        "candidate_name": candidate_name,
        "session_id": session_id,
        "recommendation": "Consider with reservations",
        "summary": "Assessment could not be fully generated. Please review the transcript manually.",
        "dimensions": {
            "communication_clarity": {
                "score": 5,
                "confidence": "low",
                "justification": "Unable to parse assessment.",
                "evidence_quote": "—"
            },
            "warmth_and_patience": {
                "score": 5,
                "confidence": "low",
                "justification": "Unable to parse assessment.",
                "evidence_quote": "—"
            },
            "ability_to_simplify": {
                "score": 5,
                "confidence": "low",
                "justification": "Unable to parse assessment.",
                "evidence_quote": "—"
            },
            "english_fluency": {
                "score": 5,
                "confidence": "low",
                "justification": "Unable to parse assessment.",
                "evidence_quote": "—"
            },
            "candidate_fit": {
                "score": 5,
                "confidence": "low",
                "justification": "Unable to parse assessment.",
                "evidence_quote": "—"
            },
        },
        "overall_score": 5.0,
        "percentile_rank": None,
        "flags": ["assessment_parsing_error"],
    }

