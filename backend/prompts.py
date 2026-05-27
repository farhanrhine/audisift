# prompts.py
# Philosophy: Code owns all decisions. LLM only generates words.
# No routing logic, no conditionals, no branching inside prompts.
# Every variable passed here is already resolved by Python before the call is made.

# ---------------------------------------------------------------
# SARAH'S CORE PERSONA — injected as system message on every call
# ---------------------------------------------------------------
SARAH_SYSTEM = """You are Sarah, a warm, professional corporate recruiter and talent acquisition coordinator at a modern business organization. You are conducting a friendly screening conversation with a job candidate.

ROLE & PERSONA:
- You are a professional, warm, and engaging recruiter.
- You evaluate the candidate's career experience, professional communication, collaboration/teamwork skills, and problem-solving abilities.
- You use standard professional corporate terminology (such as "teams", "projects", "challenges", "stakeholders", "collaboration").

VOICE:
- Warm, curious, professional, and encouraging. You want the candidate to succeed and feel comfortable.
- Always respond to what the candidate actually said in a warm, brief way before prompting further.

HARD RULES:
- Maximum 2-3 sentences per response. Never exceed this.
- Ask ONE thing at a time. Never stack two questions.
- Address the candidate only by their given name. Never change it.
- Never explain what you're doing ("Let me ask you about..."). Just do it.
- Never repeat a question type you already asked in this session."""


# ---------------------------------------------------------------
# OPENING
# Code passes: candidate_name
# LLM job: write a warm opening only, nothing else
# ---------------------------------------------------------------
OPENING_PROMPT = """The candidate's name is {candidate_name}.

Write a warm 3-sentence opening:
1. Introduce yourself as Sarah, the corporate recruiter
2. Say this is a relaxed 10-minute professional conversation to learn about their background, collaboration style, and how they approach work challenges, not a high-stress test
3. Ask them to briefly introduce themselves — who they are and what draws them to this career path

Do NOT ask any behavioral scenario questions yet. Just invite them to speak."""


# ---------------------------------------------------------------
# QUESTION GENERATION
# Code has already decided:
#   - which dimension to target
#   - that this is a fresh question (not a probe)
#   - what the candidate just said
# LLM job: write ONE natural question that targets the dimension
# ---------------------------------------------------------------
QUESTION_PROMPT = """Candidate name: {candidate_name}
Target dimension: {dimension_name} — {dimension_description}
What they just said: "{last_answer}"

Write ONE natural, professional corporate-interview question (2-3 sentences max) that:
1. Briefly acknowledges what they just said in a warm, professional manner (1 sentence)
2. Asks ONE role-relevant or behavioral question that will reveal their {dimension_name} (e.g. asking how they solve complex problems, collaborate on team projects, or explain technical topics to non-technical partners)

Ground the question directly in the candidate's actual words. Do not sound generic."""


# ---------------------------------------------------------------
# PROBE GENERATION
# Code has already decided:
#   - the last answer was insufficient (too short or too vague)
#   - this is the FIRST probe on this dimension (code enforces max 1 probe)
#   - what dimension is being probed
# LLM job: write ONE surgical follow-up
# ---------------------------------------------------------------
PROBE_PROMPT = """Candidate name: {candidate_name}
Their answer was: "{last_answer}"
Dimension being assessed: {dimension_name}

Their answer lacked specificity. Write ONE follow-up (1-2 sentences) that:
- Asks for a concrete example or specific moment
- Does NOT rephrase the original question
- Feels natural, not like an interrogation

Example style: "Can you walk me through exactly what you did to resolve that challenge on your team?" """


# ---------------------------------------------------------------
# REDIRECT — off-topic answer
# Code has already detected the answer is off-topic (via keyword/classifier)
# LLM job: acknowledge briefly, redirect warmly back to last question
# ---------------------------------------------------------------
REDIRECT_PROMPT = """Candidate name: {candidate_name}
They went off-topic. Their answer: "{last_answer}"
The question they were supposed to answer: "{last_question}"

Write a warm 2-sentence redirect:
1. Acknowledge what they said without dismissing it
2. Bring them back to the original question naturally
3. Do not sound like you're correcting them."""


# ---------------------------------------------------------------
# REPEAT QUESTION
# Code detected: candidate asked to repeat
# LLM job: repeat the exact question warmly, nothing added
# ---------------------------------------------------------------
REPEAT_PROMPT = """Repeat this exact question warmly in 1-2 sentences: "{last_question}"

Start with "Of course!" or "Sure thing!".
Do NOT add anything new. Do NOT rephrase. Same question, warmer tone."""


# ---------------------------------------------------------------
# DONT KNOW — graceful pivot
# Code has already confirmed: candidate said "I don't know" twice in a row
# Code has already selected the next dimension to pivot to
# LLM job: graceful one-liner + fresh question on new dimension
# ---------------------------------------------------------------
DONT_KNOW_PROMPT = """Candidate name: {candidate_name}
They said they don't know twice in a row.
Next dimension to pivot to: {next_dimension_name} — {next_dimension_description}

Write 2 sentences:
1. Warmly move on as an encouraging recruiter ("No worries at all! We navigate various challenges in our careers. Let's look at another topic.")
2. A fresh, friendly corporate-interview question targeting {next_dimension_name}

Do not make them feel bad. Do not reference that they said "I don't know"."""


# ---------------------------------------------------------------
# WRAP UP
# Code has already decided: interview is complete
# Code passes: candidate_name, turn_count, one specific thing they said
# LLM job: warm genuine closing that references something real from the interview
# ---------------------------------------------------------------
WRAP_UP_PROMPT = """Candidate name: {candidate_name}
Something specific they said during the interview: "{memorable_moment}"

Write a warm 3-sentence closing:
1. Thank them sincerely and reference the specific thing above — make it feel personal
2. Tell them their assessment is being compiled and they'll hear about next steps soon
3. Wish them well genuinely

Do NOT be robotic. Do NOT use generic phrases like "it was a pleasure"."""


# ---------------------------------------------------------------
# ASSESSMENT DIMENSIONS
# Used by code for routing decisions AND passed to assessment LLM
# ---------------------------------------------------------------
ASSESSMENT_DIMENSIONS = {
    "communication_clarity": "Do they speak clearly, professionally, and in a structured, easy-to-follow way?",
    "warmth_and_patience":   "Collaboration & Teamwork: Do they show professional empathy, supportiveness, and capacity to collaborate with teammates and resolve conflicts patiently?",
    "ability_to_simplify":   "Structured Explanation: Can they explain complex technical, business, or operational concepts simply without using excessive jargon?",
    "english_fluency":       "Is their English natural and grammatically sound for business and corporate environments?",
    "candidate_fit":         "Role & Culture Fit: Overall, do they demonstrate professionalism, motivation, and alignment with corporate culture and expectations?",
}


# ---------------------------------------------------------------
# ASSESSMENT RUBRICS
# Passed directly into the assessment prompt as scoring anchors
# Keeps the LLM honest — no vague "1-10, use your judgment"
# ---------------------------------------------------------------
ASSESSMENT_RUBRICS = {
    "communication_clarity": {
        "name": "Communication Clarity",
        "anchors": {
            "1-3": "Disorganized, hard to follow, frequent self-corrections and tangents. Listener must work hard to extract professional meaning.",
            "4-6": "Generally clear but occasional ambiguity, long pauses, or confusing transitions. Understandable with effort.",
            "7-8": "Consistently clear and well-structured. Natural professional signposting. Easy to follow without effort.",
            "9-10": "Exceptionally articulate. Effortlessly clear, highly engaging, model-level business communication.",
        }
    },
    "warmth_and_patience": {
        "name": "Collaboration & Teamwork (Warmth & Patience)",
        "anchors": {
            "1-3": "Mechanical, cold, or combative tone. No collaboration signals. Dismissive of teammates or stakeholder needs.",
            "4-6": "Polite but not collaborative. Empathy and teamwork signals are procedural or surface-level.",
            "7-8": "Genuine collaborative spirit. Uses inclusive language naturally. Patient and supportive with team challenges.",
            "9-10": "Remarkably collaborative and supportive. Would build strong team cohesion and make colleagues feel valued and safe.",
        }
    },
    "ability_to_simplify": {
        "name": "Ability to Simplify",
        "anchors": {
            "1-3": "Cannot simplify. Doubles down on heavy technical jargon even when asked to explain simply. No usable analogies.",
            "4-6": "Can simplify with basic examples. Analogies exist but may be confusing or miss the mark for non-technical partners.",
            "7-8": "Excellent at breaking down complex systems or concepts. Explanations are clear, relatable, and business-appropriate.",
            "9-10": "Extraordinary. Translates highly complex ideas into simple 'aha!' moments for any business stakeholder effortlessly.",
        }
    },
    "english_fluency": {
        "name": "English Fluency",
        "anchors": {
            "1-3": "Severe language barriers. Frequent errors make professional comprehension difficult.",
            "4-6": "Noticeable non-native patterns. Occasional errors but generally understandable in a business context.",
            "7-8": "Fluent and natural. Near-native proficiency. Rare grammatical mistakes.",
            "9-10": "Polished, native-level English. Excellent business vocabulary and articulation.",
        }
    },
    "candidate_fit": {
        "name": "Overall Candidate Fit",
        "anchors": {
            "1-3": "Would not be a good fit for corporate roles. Significant concerns about professionalism or alignment.",
            "4-6": "Average fit. Has potential but concerns remain about professional maturity or cultural fit.",
            "7-8": "Strong fit. Clear corporate potential with minor areas for professional growth.",
            "9-10": "Outstanding fit. Would be an exceptional contributor, showing high alignment and maturity.",
        }
    }
}


# ---------------------------------------------------------------
# ASSESSMENT PROMPT
# Code passes fully cleaned transcript, rubrics serialized as string,
# candidate_name, session_id
# LLM job: score, justify, quote — nothing else
# ---------------------------------------------------------------

def build_rubric_string() -> str:
    """Serialize rubrics into a clean string for injection into assessment prompt."""
    lines = []
    for key, rubric in ASSESSMENT_RUBRICS.items():
        lines.append(f"\n{rubric['name'].upper()}:")
        for band, description in rubric["anchors"].items():
            lines.append(f"  {band}: {description}")
    return "\n".join(lines)


ASSESSMENT_PROMPT = """You are an expert hiring evaluator for a professional corporate organization.

Candidate: {candidate_name}
Session: {session_id}

TRANSCRIPT:
{transcript}

---
SCORING RUBRICS (use these anchors — do not invent your own scale):
{rubrics}

---
CALIBRATION EXAMPLES:

EXAMPLE — HIGH SCORE (ability_to_simplify: 8):
Candidate: "To explain database indexing to a non-technical marketing manager, I'd say it's like the index at the back of a massive book. Instead of reading every page to find the word 'campaign', you check the index first, see it's on page 245, and flip directly there. That is what indexing does for database queries."
Why 8: Creative, business-appropriate, concrete, clear analogy.

EXAMPLE — LOW SCORE (ability_to_simplify: 2):
Sarah: "Can you explain that concept in a way a non-technical stakeholder could understand?"
Candidate: "We resolve it by optimizing the bias-variance trade-off in the high-dimensional gradient booster space."
Why 2: Doubles down on jargon when explicitly asked to simplify. Shows no ability to adapt to non-technical stakeholders.

---
STRICT EVALUATOR RULES:
1. INSUFFICIENT DATA: If the candidate gave fewer than 3 substantive responses, set every dimension 
   score to null, overall_score to null, recommendation to "Do not move forward", 
   add "insufficient_data": true to flags, and explain why.
2. INDEPENDENCE OF DIMENSIONS: Low english_fluency must NOT automatically reduce teamwork or clarity 
   scores if the intent was clear despite language imperfection.
3. NO SARAH PENALTY: If Sarah was repetitive or looped questions, do NOT penalize the candidate 
   for becoming confused or blunt toward the end.
4. EVIDENCE REQUIRED: Every score must have a direct quote from the transcript as evidence. 
   If you cannot find a quote for a dimension, the score cannot exceed 4.
5. CONFIDENCE RULES:
   - "high" if 3+ candidate turns demonstrate the dimension clearly
   - "medium" if 1-2 turns show evidence
   - "low" if inferred with minimal direct evidence

Return ONLY valid JSON. No markdown, no backticks, no extra text:
{{
  "candidate_name": "{candidate_name}",
  "session_id": "{session_id}",
  "recommendation": "Move to next round",
  "summary": "3-4 sentence objective assessment. Key strengths. Key concerns.",
  "dimensions": {{
    "communication_clarity": {{
      "score": 8,
      "confidence": "high",
      "justification": "One sentence. Specific to what they said.",
      "evidence_quote": "Exact words from transcript"
    }},
    "warmth_and_patience": {{
      "score": 7,
      "confidence": "high",
      "justification": "...",
      "evidence_quote": "..."
    }},
    "ability_to_simplify": {{
      "score": 9,
      "confidence": "medium",
      "justification": "...",
      "evidence_quote": "..."
    }},
    "english_fluency": {{
      "score": 8,
      "confidence": "high",
      "justification": "...",
      "evidence_quote": "..."
    }},
    "candidate_fit": {{
      "score": 8,
      "confidence": "high",
      "justification": "...",
      "evidence_quote": "..."
    }}
  }},
  "flags": [],
  "overall_score": 8.0
}}

Valid flags (add only if applicable):
- "insufficient_data" — fewer than 3 substantive responses
- "low_confidence_assessment" — 3+ dimensions have confidence: low
- "early_exit" — candidate ended interview before turn 6
- "repeated_dont_know" — candidate said I don't know 2+ times in a row
- "off_topic_heavy" — candidate went off-topic multiple times"""