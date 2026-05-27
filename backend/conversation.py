"""Interview engine using LangGraph with state machine and backward compatibility."""

import re
import json
from typing import TypedDict, Optional
from datetime import datetime
from groq import AsyncGroq
from langgraph.graph import StateGraph, END

try:
    from backend.config import GROQ_API_KEY, CONVERSATION_MODEL
    from backend.prompts import (
        SARAH_SYSTEM,
        ASSESSMENT_DIMENSIONS,
        OPENING_PROMPT,
        QUESTION_PROMPT,
        PROBE_PROMPT,
        REPEAT_PROMPT,
        DONT_KNOW_PROMPT,
        WRAP_UP_PROMPT,
    )
    from backend.database import update_session_state
except ImportError:
    from config import GROQ_API_KEY, CONVERSATION_MODEL
    from prompts import (
        SARAH_SYSTEM,
        ASSESSMENT_DIMENSIONS,
        OPENING_PROMPT,
        QUESTION_PROMPT,
        PROBE_PROMPT,
        REPEAT_PROMPT,
        DONT_KNOW_PROMPT,
        WRAP_UP_PROMPT,
    )
    from database import update_session_state

client = AsyncGroq(api_key=GROQ_API_KEY)


# ============================================================================
# STATE DEFINITION
# ============================================================================

class InterviewState(TypedDict):
    """State schema for LangGraph interview state machine."""
    session_id: str
    candidate_name: str
    messages: list[dict]
    dimensions_covered: list[str]
    dimensions_uncovered: list[str]
    dimensions_scores: dict[str, Optional[int]]
    follow_up_count: int
    short_answer_count: int
    dont_know_count: int
    current_dimension: Optional[str]
    turn_count: int
    exchange_count: int
    interview_complete: bool
    end_reason: Optional[str]
    last_sarah_message: str
    is_repeat_request: bool
    last_answer_quality: Optional[str]
    time_remaining: str  # Passed from frontend (e.g. "09:30")


# ============================================================================
# REGEX PATTERNS
# ============================================================================
# PURE-CODE DECISION HELPERS  (no LLM calls — deterministic)
# ============================================================================

REPEAT_RE = re.compile(
    r"\b(repeat|again|pardon|say that again|what (was|were|did) you (ask|say)|"
    r"didn'?t (hear|catch|understand)|can you say|come again|huh|sorry\??)\b",
    re.IGNORECASE,
)

DONT_KNOW_RE = re.compile(
    r"^(i don'?t know|idk|no idea|not sure|i'?m not sure|"
    r"i have no idea|nothing|i can'?t|i cannot|i give up)[\.\!\?]*$",
    re.IGNORECASE,
)

# Answer quality thresholds — code owns these numbers
_SHORT_WORD_THRESHOLD  = 12   # under this → "short"
_VAGUE_WORD_THRESHOLD  = 30   # under this → "vague"
# above _VAGUE_WORD_THRESHOLD  → "strong"

# Time thresholds (seconds)
_FORCE_WRAP_SECONDS = 30   # server-side: if <= 30s remain, always wrap up


def _parse_time_seconds(time_str: str) -> int:
    """
    Convert "MM:SS" string from frontend into total seconds.
    Returns 9999 if the string is malformed (safe default = don't force wrap).
    """
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, AttributeError):
        pass
    return 9999  # safe default


# ============================================================================
# LLM CALL HELPERS
# ============================================================================

async def _call_with_history(messages: list[dict], prompt: str) -> str:
    """Call LLM with conversation history."""
    llm_messages = [
        {"role": "system", "content": SARAH_SYSTEM},
        *messages,
        {"role": "system", "content": prompt},
    ]
    return await _groq(llm_messages)


async def _call_simple(prompt: str) -> str:
    """Call LLM with just the prompt."""
    return await _groq([{"role": "user", "content": prompt}])


async def _groq(messages: list[dict]) -> str:
    """Call Groq API."""
    try:
        response = await client.chat.completions.create(
            model=CONVERSATION_MODEL,
            messages=messages,
            max_tokens=350,
            temperature=0.8,
        )
        content = response.choices[0].message.content.strip()
        if not content:
            print("[LLM Error] Returned empty content.")
            return "I'm sorry, I didn't quite catch how to respond to that. Could we move on to the next topic?"
        return content
    except Exception as e:
        print(f"[LLM Exception] {str(e)}")
        return "I apologize, my system had a brief hiccup. Let's continue."


async def _assess_quality(answer: str, _last_question: str) -> str:
    """
    Classify answer quality using pure word-count thresholds.
    Code owns this decision — no LLM call.
    """
    word_count = len(answer.split())
    if word_count < _SHORT_WORD_THRESHOLD:
        return "short"
    if word_count < _VAGUE_WORD_THRESHOLD:
        return "vague"
    return "strong"


# ============================================================================
# LANGGRAPH NODES
# ============================================================================

async def question_node(state: InterviewState) -> InterviewState:
    """Generate Sarah's next question based on dimensions still uncovered."""
    dim_lines = "\n".join(
        f"- {dim}: {ASSESSMENT_DIMENSIONS[dim]}"
        for dim in state["dimensions_uncovered"]
    ) if state["dimensions_uncovered"] else "All dimensions covered."

    # Pick next uncovered dimension
    next_dim = state["dimensions_uncovered"][0] if state["dimensions_uncovered"] else None
    next_dim_desc = ASSESSMENT_DIMENSIONS.get(next_dim, "") if next_dim else ""
    last_answer = state["messages"][-1]["content"] if state["messages"] else ""

    # Use actual time_remaining from state (passed from frontend)
    time_remaining = state.get("time_remaining", "10:00")

    prompt = QUESTION_PROMPT.format(
        candidate_name=state["candidate_name"],
        dimension_name=next_dim or "professional background",
        dimension_description=next_dim_desc,
        last_answer=last_answer[:500] if last_answer else "just introduced themselves",
    )

    response = await _call_with_history(state["messages"], prompt)
    state["messages"].append({"role": "assistant", "content": response})
    state["last_sarah_message"] = response
    state["follow_up_count"] = 0

    return state


async def wrap_up_node(state: InterviewState) -> InterviewState:
    """Generate Sarah's closing statement."""
    # Use last candidate message as the memorable moment for personalization
    memorable = ""
    for msg in reversed(state["messages"]):
        if msg["role"] == "user" and len(msg["content"].split()) > 5:
            memorable = msg["content"][:200]
            break
    if not memorable:
        memorable = "their professional journey"
    prompt = WRAP_UP_PROMPT.format(
        candidate_name=state["candidate_name"],
        memorable_moment=memorable,
    )
    response = await _call_simple(prompt)
    state["messages"].append({"role": "assistant", "content": response})
    state["last_sarah_message"] = response
    return state


# ============================================================================
# STATE INITIALIZATION & PERSISTENCE
# ============================================================================

async def init_interview_state(
    session_id: str,
    candidate_name: str,
    exchange_count: int = 0,
    uncovered_dimensions: list = None,
    messages: list = None,
    time_remaining: str = "10:00",
) -> InterviewState:
    """Initialize interview state."""
    if uncovered_dimensions is None:
        uncovered_dimensions = list(ASSESSMENT_DIMENSIONS.keys())

    return InterviewState(
        session_id=session_id,
        candidate_name=candidate_name,
        messages=messages or [],
        dimensions_covered=[],
        dimensions_uncovered=uncovered_dimensions,
        dimensions_scores={dim: None for dim in ASSESSMENT_DIMENSIONS.keys()},
        follow_up_count=0,
        short_answer_count=0,
        dont_know_count=0,
        current_dimension=uncovered_dimensions[0] if uncovered_dimensions else None,
        turn_count=0,
        exchange_count=exchange_count,
        interview_complete=False,
        end_reason=None,
        last_sarah_message="",
        is_repeat_request=False,
        last_answer_quality=None,
        time_remaining=time_remaining,
    )


# ============================================================================
# BACKWARD-COMPATIBLE INTERVIEW ENGINE
# ============================================================================


class InterviewEngine:
    """
    Interview engine with LangGraph-based state machine.
    Maintains backward-compatible API while using state-driven interview logic.
    """

    def __init__(
        self,
        session_id: str,
        candidate_name: str,
        exchange_count: int = 0,
        uncovered_dimensions: list = None,
        messages: list = None,
    ):
        self.session_id = session_id
        self.candidate_name = candidate_name
        self.state: Optional[InterviewState] = None
        self._initialized = False
        self._init_params = {
            "exchange_count": exchange_count,
            "uncovered_dimensions": uncovered_dimensions,
            "messages": messages,
        }

    @property
    def exchange_count(self) -> int:
        if self.state:
            return self.state.get("exchange_count", 0)
        return self._init_params.get("exchange_count", 0)

    @property
    def uncovered_dimensions(self) -> list:
        if self.state:
            return self.state.get("dimensions_uncovered", [])
        return self._init_params.get("uncovered_dimensions") or list(ASSESSMENT_DIMENSIONS.keys())

    async def _ensure_initialized(self):
        """Lazy initialization of state."""
        if not self._initialized:
            self.state = await init_interview_state(
                self.session_id,
                self.candidate_name,
                **self._init_params,
            )
            self._initialized = True

    async def get_opening_message(self) -> str:
        """Get Sarah's opening message."""
        await self._ensure_initialized()
        prompt = OPENING_PROMPT.format(candidate_name=self.candidate_name)
        response = await _call_simple(prompt)
        self.state["messages"].append({"role": "assistant", "content": response})
        self.state["last_sarah_message"] = response
        try:
            await update_session_state(self.session_id, self.state)
        except:
            pass  # Graceful degradation if DB unavailable
        return response

    async def process_candidate_answer(self, answer: str, time_remaining: str = "10:00") -> dict:
        """Process candidate answer and return Sarah's response."""
        await self._ensure_initialized()
        # Update time_remaining in state so question_node uses the real value
        self.state["time_remaining"] = time_remaining

        # ---------------------------------------------------------------
        # CODE DECISION: force wrap-up if time is nearly up
        # The LLM has no authority to keep the interview going past the timer
        # ---------------------------------------------------------------
        seconds_left = _parse_time_seconds(time_remaining)
        if seconds_left <= _FORCE_WRAP_SECONDS and not self.state["interview_complete"]:
            self.state["interview_complete"] = True
            self.state["end_reason"] = "timeout"
            response_state = await wrap_up_node(self.state)
            self.state = response_state
            try:
                await update_session_state(self.session_id, self.state)
            except:
                pass
            return {
                "interviewer_response": self.state["last_sarah_message"],
                "interview_complete": True,
            }

        # ---------------------------------------------------------------
        # CODE DECISION: handle system termination signals
        # ---------------------------------------------------------------
        is_termination = answer.startswith("[") and any(
            x in answer.lower() for x in ["end", "stop", "terminate"]
        )
        if is_termination:
            self.state["interview_complete"] = True
            self.state["end_reason"] = "early"
            response_state = await wrap_up_node(self.state)
            self.state = response_state
            try:
                await update_session_state(self.session_id, self.state)
            except:
                pass
            return {
                "interviewer_response": self.state["last_sarah_message"],
                "interview_complete": True,
            }

        # Add candidate message
        self.state["messages"].append({"role": "user", "content": answer})
        self.state["turn_count"] += 1

        # Check for repeat request
        if self._is_repeat(answer):
            self.state["is_repeat_request"] = True
            response = await self._handle_repeat()
            self.state["is_repeat_request"] = False
        else:
            self.state["exchange_count"] += 1

            # Check for "I don't know"
            if DONT_KNOW_RE.match(answer.strip()):
                self.state["dont_know_count"] += 1
            else:
                self.state["dont_know_count"] = 0

            # If 2+ "I don't knows", move on
            if self.state["dont_know_count"] >= 2:
                self.state["dont_know_count"] = 0
                await self._graceful_move_on()
                response = self.state["last_sarah_message"]
            else:
                # Assess quality and determine next action
                self.state["last_answer_quality"] = await _assess_quality(
                    answer, self.state["last_sarah_message"]
                )

                # Generate next response
                if (
                    self.state["last_answer_quality"] in ("short", "vague")
                    and self.state["follow_up_count"] == 0
                ):
                    # Follow up
                    response = await self._generate_followup(answer)
                    self.state["follow_up_count"] += 1
                else:
                    # Move to next
                    await self._mark_dimension_progress()
                    if (
                        self.state["exchange_count"] >= 7
                        or not self.state["dimensions_uncovered"]
                    ):
                        self.state["interview_complete"] = True
                        response_state = await wrap_up_node(self.state)
                        self.state = response_state
                    else:
                        response_state = await question_node(self.state)
                        self.state = response_state
                    response = self.state["last_sarah_message"]

        # Persist state
        try:
            await update_session_state(self.session_id, self.state)
        except:
            pass

        return {
            "interviewer_response": response,
            "interview_complete": self.state["interview_complete"],
        }

    def _is_repeat(self, answer: str) -> bool:
        """Check if candidate is asking for repeat."""
        stripped = answer.strip().lower()
        words = stripped.split()
        if len(words) <= 7 and REPEAT_RE.search(stripped):
            return True
        if re.search(r"\b(repeat|say that again|come again)\b", stripped, re.IGNORECASE):
            return True
        return False

    async def _handle_repeat(self) -> str:
        """
        Handle repeat request with PURE CODE — no LLM call.
        Re-emits the last Sarah message with a warm prefix.
        The LLM is not needed here and would be non-deterministic.
        """
        last = self.state["last_sarah_message"]
        if not last:
            response = "Of course! To get us started, could you tell me a bit about yourself and what draws you to this career path?"
        else:
            # Code picks the prefix, LLM picks nothing
            response = f"Of course! I was asking: {last}"
        self.state["messages"].append({"role": "assistant", "content": response})
        self.state["last_sarah_message"] = response
        return response

    async def _generate_followup(self, answer: str) -> str:
        """Generate follow-up probe using PROBE_PROMPT."""
        dim = self.state.get("current_dimension", "professional background")
        prompt = PROBE_PROMPT.format(
            candidate_name=self.state["candidate_name"],
            last_answer=answer[:500],
            dimension_name=dim,
        )
        response = await _call_with_history(self.state["messages"], prompt)
        self.state["messages"].append({"role": "assistant", "content": response})
        self.state["last_sarah_message"] = response
        return response

    async def _graceful_move_on(self):
        """Move to next dimension after 'I don't know'."""
        if (
            self.state["exchange_count"] >= 7
            or not self.state["dimensions_uncovered"]
        ):
            self.state["interview_complete"] = True
            response_state = await wrap_up_node(self.state)
            self.state = response_state
        else:
            next_dim = (
                self.state["dimensions_uncovered"][0]
                if self.state["dimensions_uncovered"]
                else "candidate_fit"
            )
            next_dim_description = ASSESSMENT_DIMENSIONS.get(next_dim, "their overall professional background")
            # Use correct param names matching DONT_KNOW_PROMPT in prompts.py
            prompt = DONT_KNOW_PROMPT.format(
                candidate_name=self.state["candidate_name"],
                next_dimension_name=next_dim,
                next_dimension_description=next_dim_description,
            )
            response = await _call_with_history(self.state["messages"], prompt)
            self.state["messages"].append({"role": "assistant", "content": response})
            self.state["last_sarah_message"] = response

    async def _mark_dimension_progress(self):
        """Mark dimensions as covered."""
        if (
            self.state["exchange_count"] > 0
            and self.state["current_dimension"]
            and self.state["current_dimension"] in self.state["dimensions_uncovered"]
        ):
            self.state["dimensions_uncovered"].remove(self.state["current_dimension"])
            self.state["dimensions_covered"].append(self.state["current_dimension"])
            if self.state["dimensions_uncovered"]:
                self.state["current_dimension"] = self.state["dimensions_uncovered"][0]


def create_engine(
    session_id: str,
    candidate_name: str,
    exchange_count: int = 0,
    uncovered_dimensions: list = None,
    messages: list = None,
) -> InterviewEngine:
    """Factory function for creating interview engine instances."""
    return InterviewEngine(session_id, candidate_name, exchange_count, uncovered_dimensions, messages)
