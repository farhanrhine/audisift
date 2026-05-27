import json
import re
from groq import AsyncGroq
try:
    from backend.config import GROQ_API_KEY, ASSESSMENT_MODEL
    from backend.database import get_messages, get_session, save_assessment
    from backend.prompts import ASSESSMENT_PROMPT, ASSESSMENT_RUBRICS, build_rubric_string
except ImportError:
    from config import GROQ_API_KEY, ASSESSMENT_MODEL
    from database import get_messages, get_session, save_assessment
    from prompts import ASSESSMENT_PROMPT, ASSESSMENT_RUBRICS, build_rubric_string

client = AsyncGroq(api_key=GROQ_API_KEY)

# ============================================================================
# CODE-OWNS-DECISIONS CONSTANTS
# These are the ONLY source of truth for business rules.
# The LLM has no authority to override these.
# ============================================================================

# Recommendation thresholds — code owns this, not the LLM
_REC_MOVE_FORWARD  = 7.5   # overall_score >= this → "Move to next round"
_REC_RESERVATIONS  = 5.0   # overall_score >= this → "Consider with reservations"
# below _REC_RESERVATIONS       → "Do not move forward"

# Confidence from evidence (candidate word count per dimension)
_CONF_HIGH_WORDS   = 80    # >= this many candidate words → "high"
_CONF_MEDIUM_WORDS = 20    # >= this many candidate words → "medium"
# below _CONF_MEDIUM_WORDS        → "low"

# Valid dimension keys
_DIMENSIONS = [
    "communication_clarity",
    "warmth_and_patience",
    "ability_to_simplify",
    "english_fluency",
    "candidate_fit",
]

# Keyword signals per dimension — used to count evidence in transcript
_DIMENSION_KEYWORDS = {
    "communication_clarity": ["explain", "clear", "understand", "structure", "communicate", "describe", "articulate"],
    "warmth_and_patience":   ["team", "collaborate", "support", "help", "listen", "share", "together", "contribute", "group", "partner"],
    "ability_to_simplify":   ["simple", "analogy", "example", "break down", "easy", "relate", "imagine", "story"],
    "english_fluency":       [],  # assessed from all candidate words
    "candidate_fit":         ["culture", "fit", "values", "align", "grow", "motivation", "passion", "role", "career", "learn"],
}

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
        await save_assessment(
            session_id,
            json.dumps(report),
            recommendation=report["recommendation"],
            overall_score=report["overall_score"],
        )
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
                    "You are an expert recruiter and talent evaluator with deep knowledge of professional workplace competencies and candidate screening. "
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
    report = _extract_and_enhance_json(raw, candidate_name, session_id, flags, candidate_count, messages)

    # 6. Save to database — save_assessment also denormalizes score onto Session
    #    and sets status=completed atomically, so complete_session is not needed
    await save_assessment(
        session_id,
        json.dumps(report),
        recommendation=report.get("recommendation"),
        overall_score=report.get("overall_score"),
    )

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


# ============================================================================
# PURE-CODE DECISION FUNCTIONS
# All business decisions live here — not in the LLM output
# ============================================================================

def _clamp_score(score) -> float:
    """Clamp score to valid range [1, 10]. Code enforces bounds, LLM doesn't."""
    try:
        s = float(score)
        return round(max(1.0, min(10.0, s)), 1)
    except (TypeError, ValueError):
        return 5.0  # safe neutral fallback


def _compute_overall_score(dimensions: dict) -> float:
    """
    Always compute overall_score from dimension scores in Python.
    Never trust the LLM's self-computed average.
    """
    scores = [dimensions.get(k, {}).get("score", 5.0) for k in _DIMENSIONS]
    return round(sum(scores) / len(scores), 1)


def _compute_recommendation(overall_score: float) -> str:
    """
    Compute hiring recommendation from score using fixed thresholds.
    This is a business decision — code owns it, not the LLM.
    """
    if overall_score >= _REC_MOVE_FORWARD:
        return "Move to next round"
    if overall_score >= _REC_RESERVATIONS:
        return "Consider with reservations"
    return "Do not move forward"


def _compute_evidence_word_counts(messages: list[dict]) -> dict[str, int]:
    """
    Count how many candidate words exist that signal each dimension.
    Returns {dimension_key: word_count} for confidence override.
    """
    candidate_text = " ".join(
        m["content"].lower()
        for m in messages
        if m.get("role") == "candidate"
    )
    total_candidate_words = len(candidate_text.split())

    counts = {}
    for dim in _DIMENSIONS:
        if dim == "english_fluency":
            # Fluency is assessed from ALL candidate words
            counts[dim] = total_candidate_words
        else:
            keywords = _DIMENSION_KEYWORDS.get(dim, [])
            if keywords:
                dim_words = sum(
                    candidate_text.count(kw) * 5  # weight: each keyword ~ 5 relevant words
                    for kw in keywords
                )
                # Also add base word count proportionally
                counts[dim] = dim_words + (total_candidate_words // len(_DIMENSIONS))
            else:
                counts[dim] = total_candidate_words // len(_DIMENSIONS)
    return counts


def _override_confidence(dim_key: str, evidence_words: int) -> str:
    """
    Override LLM confidence with evidence-based logic.
    Code counts the evidence, LLM just claims confidence — we trust code.
    """
    if evidence_words >= _CONF_HIGH_WORDS:
        return "high"
    if evidence_words >= _CONF_MEDIUM_WORDS:
        return "medium"
    return "low"



def _extract_and_enhance_json(
    raw: str,
    candidate_name: str,
    session_id: str,
    flags: list,
    candidate_count: int,
    messages: list[dict],
) -> dict:
    """
    Extract JSON from LLM output and add Phase 4 enhancements.
    Enforces Code-Owns-Decisions rules (clamps scores, overrides confidence,
    recomputes overall_score and recommendation).
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

    # Pre-calculate evidence word counts for confidence overrides
    evidence_counts = _compute_evidence_word_counts(messages)

    # Clean, clamp and override confidence for all 5 dimensions
    for dim_key in _DIMENSIONS:
        if dim_key not in report["dimensions"]:
            report["dimensions"][dim_key] = {
                "score": 5.0,
                "confidence": "low",
                "justification": "Insufficient data.",
                "evidence_quote": "—"
            }
        else:
            dim_data = report["dimensions"][dim_key]
            if not isinstance(dim_data, dict):
                dim_data = {"score": 5.0, "justification": str(dim_data), "evidence_quote": "—"}
                report["dimensions"][dim_key] = dim_data
            
            # 1. Clamp score in [1.0, 10.0]
            dim_data["score"] = _clamp_score(dim_data.get("score", 5.0))
            
            # 2. Evidence-based confidence override (Code owns this!)
            words = evidence_counts.get(dim_key, 0)
            dim_data["confidence"] = _override_confidence(dim_key, words)
            
            # Ensure quote fields exist
            if "evidence_quote" not in dim_data:
                dim_data["evidence_quote"] = "—"
            if "justification" not in dim_data:
                dim_data["justification"] = "No justification provided."

    # 3. Always recompute overall score from dimension scores in Python
    report["overall_score"] = _compute_overall_score(report["dimensions"])

    # 4. Always compute recommendation from score thresholds in Python
    report["recommendation"] = _compute_recommendation(report["overall_score"])

    # Add flags for data quality
    if "flags" not in report:
        report["flags"] = []
    
    # Merge flags from analysis
    for f in flags:
        if f not in report["flags"]:
            report["flags"].append(f)
    
    # If 3+ dimensions have low confidence, add insufficient_data flag
    low_confidence_count = sum(
        1 for dim in report["dimensions"].values()
        if dim.get("confidence") == "low"
    )
    if low_confidence_count >= 3 and "insufficient_data" not in report["flags"]:
        report["flags"].append("insufficient_data")

    # Add percentile_rank (placeholder, nullable for now)
    if "percentile_rank" not in report:
        report["percentile_rank"] = None

    # Ensure other fields
    report.setdefault("candidate_name", candidate_name)
    report.setdefault("session_id", session_id)
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

