import logging

from app.schemas.interview import InterviewQuestion, InterviewQuestionSet
from app.services import llm_router
from app.services.llm_router import TaskComplexity

logger = logging.getLogger(__name__)

TOTAL_QUESTIONS = 8

# technical 40%, behavioral 30%, situational 20%, culture 10%
_CATEGORY_WEIGHTS = {
    "technical": 0.4,
    "behavioral": 0.3,
    "situational": 0.2,
    "culture": 0.1,
}


def _category_counts(total: int) -> dict[str, int]:
    """Splits `total` questions across categories by weight, largest-remainder first
    so the counts always sum exactly to `total` regardless of rounding."""
    raw = {cat: weight * total for cat, weight in _CATEGORY_WEIGHTS.items()}
    counts = {cat: int(value) for cat, value in raw.items()}
    remainder = total - sum(counts.values())

    remainder_order = sorted(raw, key=lambda cat: raw[cat] - counts[cat], reverse=True)
    for cat in remainder_order[:remainder]:
        counts[cat] += 1
    return counts


def _resume_gaps(jd_data: dict, resume_data: dict) -> list[str]:
    required = {s.lower() for s in jd_data.get("required_skills", [])}
    have = {s.lower() for s in resume_data.get("skills", [])}
    missing = required - have
    return [s for s in jd_data.get("required_skills", []) if s.lower() in missing]


async def generate_questions(jd_data: dict, resume_data: dict, total: int = TOTAL_QUESTIONS) -> list[InterviewQuestion]:
    """Generates a personalized, mixed-category question set from JD requirements,
    resume gaps, and seniority — using a chain-of-thought prompt so the model
    justifies *why* each question fits this specific candidate/role pairing."""
    counts = _category_counts(total)
    gaps = _resume_gaps(jd_data, resume_data)
    seniority = jd_data.get("seniority_level") or "unspecified"

    prompt = (
        "You are an expert technical interviewer designing a personalized interview.\n\n"
        f"Role: {jd_data.get('title')}\n"
        f"Seniority level: {seniority}\n"
        f"Required skills: {', '.join(jd_data.get('required_skills', [])) or 'none listed'}\n"
        f"Nice-to-have skills: {', '.join(jd_data.get('nice_to_have_skills', [])) or 'none listed'}\n"
        f"Responsibilities: {', '.join(jd_data.get('responsibilities', [])) or 'none listed'}\n\n"
        f"Candidate skills: {', '.join(resume_data.get('skills', [])) or 'none listed'}\n"
        f"Candidate experience: {resume_data.get('experience_years') or '?'} years\n"
        f"Skill gaps (required by the role but not evidenced on the resume): "
        f"{', '.join(gaps) or 'none — strong skill coverage'}\n\n"
        f"Generate exactly {total} interview questions with this category mix:\n"
        f"- technical: {counts['technical']}\n"
        f"- behavioral: {counts['behavioral']}\n"
        f"- situational: {counts['situational']}\n"
        f"- culture: {counts['culture']}\n\n"
        "For each question, think step by step about what it probes for this specific "
        "candidate and role — favor questions that test the skill gaps above and match "
        "the seniority level — then write that reasoning into `rationale`. "
        "`category` must be exactly one of: technical, behavioral, situational, culture."
    )

    llm, model_name = llm_router.get_llm(TaskComplexity.COMPLEX, estimated_tokens=llm_router.estimate_tokens(prompt))
    structured_llm = llm.with_structured_output(InterviewQuestionSet, include_raw=True)
    result = await structured_llm.ainvoke(prompt)
    parsed: InterviewQuestionSet = result["parsed"]

    input_tokens, output_tokens = llm_router.extract_usage(result["raw"])
    await llm_router.log_cost("generate_interview_questions", model_name, input_tokens, output_tokens)

    if not parsed.questions:
        logger.warning("question_generator produced an empty question set; falling back to a generic set")
        return [
            InterviewQuestion(
                question=f"Tell me about your experience relevant to {jd_data.get('title', 'this role')}.",
                category="behavioral",
                rationale="Fallback question used because generation returned no questions.",
            )
        ]
    return parsed.questions
