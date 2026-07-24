import logging

from app.schemas.report import ReportSchema
from app.services import llm_router
from app.services.llm_router import TaskComplexity

logger = logging.getLogger(__name__)

# Two calibration examples spanning the recommendation spectrum (a strong senior
# hire and a clear reject) so the model anchors its scoring scale and tone
# instead of drifting toward an all-positive or all-negative default.
_FEW_SHOT_EXAMPLES = """\
--- EXAMPLE 1 ---
Input:
Role: Senior Backend Engineer (required: Python, FastAPI, Kubernetes, System Design)
Candidate: 6 years experience, skills: Python, FastAPI, PostgreSQL, Kubernetes, Docker
Match score: 91/100
Interview transcript summary: Gave a detailed, correct answer on designing a scalable
microservice architecture including service discovery and connection pooling. Described
a concrete past incident mentoring two junior engineers with measurable outcomes. One
situational question on handling a missed deadline was answered adequately but generically.

Output:
{
  "overall_score": 8.7,
  "recommendation": "Strongly Hire",
  "technical_assessment": {
    "score": 9.0,
    "strengths": ["Deep FastAPI/Kubernetes knowledge", "Clear systems-design reasoning", "Names concrete tools and tradeoffs, not just buzzwords"],
    "gaps": ["Did not mention observability/monitoring unprompted"],
    "comments": "Consistently answered with specific, technically correct detail rather than generic textbook answers."
  },
  "communication_assessment": {
    "score": 8.5,
    "clarity": "Structured answers logically, led with the approach then filled in detail.",
    "articulation": "Explained tradeoffs in plain language accessible to non-specialists.",
    "examples": ["Described the mentoring incident with a specific measurable outcome (cut incident time by half)."]
  },
  "culture_fit": {
    "score": 8.0,
    "comments": "Demonstrated ownership and a coaching mindset toward junior engineers."
  },
  "skill_breakdown": [
    {"skill": "Python/FastAPI", "proficiency_level": "Expert", "evidence": "Detailed, accurate architecture answer unprompted for follow-up detail."},
    {"skill": "Kubernetes", "proficiency_level": "Advanced", "evidence": "Correctly addressed deployment considerations when asked directly."},
    {"skill": "Mentoring/Leadership", "proficiency_level": "Advanced", "evidence": "Concrete mentoring example with measurable results."}
  ],
  "interview_highlights": {
    "best_answer": "The microservice architecture design answer — specific, well-reasoned, covered failure modes.",
    "concern_answer": "The missed-deadline situational answer was correct but generic, lacking a concrete example."
  },
  "suggested_next_steps": "Move to final-round system design interview with the engineering lead; no additional screening needed.",
  "red_flags": []
}

--- EXAMPLE 2 ---
Input:
Role: Senior Backend Engineer (required: Python, FastAPI, Kubernetes, System Design)
Candidate: 1 year experience, skills: HTML, CSS, jQuery
Match score: 22/100
Interview transcript summary: Could not describe how to design a scalable system when
asked directly ("I dunno, just use some servers and databases"), and after a follow-up
still gave only a vague, non-technical answer. Mentoring question answered with an
unrelated technical tangent, suggesting difficulty following the conversation.

Output:
{
  "overall_score": 2.1,
  "recommendation": "Reject",
  "technical_assessment": {
    "score": 1.5,
    "strengths": [],
    "gaps": ["No demonstrated backend/systems knowledge", "Could not answer even after a follow-up prompt", "Skill set (HTML/CSS/jQuery) does not match the role's core requirements"],
    "comments": "Answers stayed vague even when directly prompted for specifics, indicating the required technical depth is not there."
  },
  "communication_assessment": {
    "score": 3.0,
    "clarity": "Answers were short and did not directly address what was asked.",
    "articulation": "Struggled to explain technical concepts at any level of depth.",
    "examples": ["Responded to a mentoring question with an unrelated technical tangent, missing the question's intent."]
  },
  "culture_fit": {
    "score": 4.0,
    "comments": "Insufficient signal to assess culture fit meaningfully given the technical mismatch."
  },
  "skill_breakdown": [
    {"skill": "Python/FastAPI", "proficiency_level": "Beginner", "evidence": "No FastAPI/Python experience listed and no relevant answers given."},
    {"skill": "System Design", "proficiency_level": "Beginner", "evidence": "Could not produce a coherent design even with a follow-up prompt."}
  ],
  "interview_highlights": {
    "best_answer": "No answer stood out as a strength.",
    "concern_answer": "The system design question: gave no concrete approach even after a targeted follow-up."
  },
  "suggested_next_steps": "Do not proceed. Skill set is not aligned with this role; consider only if a junior/frontend opening exists.",
  "red_flags": ["Resume skills do not match the role's core requirements", "Unable to answer core technical question even with a follow-up"]
}
"""


def _format_transcript(exchanges: list[dict]) -> str:
    lines = []
    for ex in exchanges:
        tag = " (follow-up)" if ex.get("is_follow_up") else ""
        lines.append(f"Q [{ex.get('category')}]{tag}: {ex.get('question')}")
        lines.append(f"A: {ex.get('answer')}")
        if ex.get("score") is not None:
            lines.append(f"(scored {ex['score']}/5 during the interview — {ex.get('feedback')})")
        lines.append("")
    return "\n".join(lines)


async def generate_report(
    resume_data: dict,
    jd_data: dict,
    interview_exchanges: list[dict],
    match_score: float | None,
) -> ReportSchema:
    """Generates a structured hiring report via GPT-4o, few-shot-anchored against
    two calibration examples spanning the recommendation spectrum."""
    match_score_line = f"{match_score:.0f}/100" if match_score is not None else "not yet computed"

    prompt = (
        "You are a senior technical recruiter writing an objective, evidence-based hiring "
        "report from an interview transcript. Base every claim on specific evidence from the "
        "resume or transcript below — do not invent skills or achievements not mentioned. "
        "Calibrate your scores and recommendation the way the examples below do: reserve "
        "'Strongly Hire' for candidates who gave specific, correct, detailed answers, and "
        "'Reject' for candidates who couldn't answer core questions even after a follow-up.\n\n"
        f"{_FEW_SHOT_EXAMPLES}\n"
        "--- NOW GENERATE A REPORT FOR THIS CANDIDATE ---\n"
        "Input:\n"
        f"Role: {jd_data.get('title')} (required: {', '.join(jd_data.get('required_skills', [])) or 'none listed'})\n"
        f"Candidate: {resume_data.get('experience_years') or '?'} years experience, "
        f"skills: {', '.join(resume_data.get('skills', [])) or 'none listed'}\n"
        f"Match score: {match_score_line}\n"
        f"Interview transcript:\n{_format_transcript(interview_exchanges)}\n"
        "Output:"
    )

    parsed = await llm_router.invoke_structured_with_fallback(
        TaskComplexity.COMPLEX, "generate_candidate_report", prompt, ReportSchema
    )

    return parsed
