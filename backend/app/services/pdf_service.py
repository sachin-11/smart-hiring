import io
import logging

import matplotlib

matplotlib.use("Agg")  # headless — no display/GUI backend on the server
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.report import ReportSchema

logger = logging.getLogger(__name__)

_PROFICIENCY_SCORE = {"Beginner": 1, "Intermediate": 2, "Advanced": 3, "Expert": 4}

_RECOMMENDATION_COLOR = {
    "Strongly Hire": colors.HexColor("#059669"),
    "Hire": colors.HexColor("#65a30d"),
    "Hold": colors.HexColor("#d97706"),
    "Reject": colors.HexColor("#dc2626"),
}


def _skill_chart_image(skill_breakdown: list) -> Image | None:
    if not skill_breakdown:
        return None

    skills = [item.skill for item in skill_breakdown]
    scores = [_PROFICIENCY_SCORE.get(item.proficiency_level, 0) for item in skill_breakdown]

    fig, ax = plt.subplots(figsize=(6, 0.4 * len(skills) + 0.6))
    ax.barh(skills, scores, color="#4f46e5")
    ax.set_xlim(0, 4)
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["Beginner", "Intermediate", "Advanced", "Expert"], fontsize=8)
    ax.invert_yaxis()
    ax.set_title("Skill Breakdown", fontsize=11, loc="left")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)

    return Image(buf, width=6 * inch, height=(0.4 * len(skills) + 0.6) * inch)


def _candidate_photo_placeholder(candidate_name: str | None) -> Table:
    """No candidate-photo upload feature exists in this app yet — render a
    circular initials avatar in its place rather than fabricating an image."""
    initials = "".join(part[0].upper() for part in (candidate_name or "?").split()[:2]) or "?"
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#e0e7ff")),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor("#4338ca")),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
            ("FONTSIZE", (0, 0), (0, 0), 20),
            ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
            ("BOX", (0, 0), (0, 0), 0, colors.white),
        ]
    )
    table = Table([[initials]], colWidths=[0.7 * inch], rowHeights=[0.7 * inch])
    table.setStyle(style)
    return table


def _company_logo_placeholder() -> Table:
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor("#64748b")),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
            ("FONTSIZE", (0, 0), (0, 0), 8),
        ]
    )
    table = Table([["COMPANY\nLOGO"]], colWidths=[1.0 * inch], rowHeights=[0.5 * inch])
    table.setStyle(style)
    return table


def build_report_pdf(
    report: ReportSchema,
    candidate_name: str | None,
    job_title: str | None,
) -> bytes:
    """Renders a candidate scorecard PDF and returns it as bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
    )

    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=9, textColor=colors.HexColor("#475569"))

    story = []

    header_table = Table(
        [[_company_logo_placeholder(), Paragraph("Candidate Scorecard", h1), _candidate_photo_placeholder(candidate_name)]],
        colWidths=[1.2 * inch, 4.1 * inch, 1.2 * inch],
    )
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(header_table)
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(candidate_name or "Unknown Candidate", h2))
    story.append(Paragraph(f"Role: {job_title or 'Unknown Role'}", body))
    story.append(Spacer(1, 0.1 * inch))

    rec_color = _RECOMMENDATION_COLOR.get(report.recommendation, colors.grey)
    score_table = Table(
        [[f"Overall Score: {report.overall_score:.1f} / 10", report.recommendation.upper()]],
        colWidths=[3.2 * inch, 3.2 * inch],
    )
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (1, 0), (1, 0), rec_color),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 0.2 * inch))

    def _assessment_section(title: str, score: float, lines: list[str]) -> None:
        story.append(Paragraph(f"{title} — {score:.1f}/10", h2))
        for line in lines:
            story.append(Paragraph(line, body))
        story.append(Spacer(1, 0.1 * inch))

    ta = report.technical_assessment
    _assessment_section(
        "Technical Assessment",
        ta.score,
        [
            ta.comments,
            f"<b>Strengths:</b> {', '.join(ta.strengths) or '—'}",
            f"<b>Gaps:</b> {', '.join(ta.gaps) or '—'}",
        ],
    )

    ca = report.communication_assessment
    _assessment_section(
        "Communication Assessment",
        ca.score,
        [
            f"<b>Clarity:</b> {ca.clarity}",
            f"<b>Articulation:</b> {ca.articulation}",
        ],
    )

    cf = report.culture_fit
    _assessment_section("Culture Fit", cf.score, [cf.comments])

    chart = _skill_chart_image(report.skill_breakdown)
    if chart:
        story.append(chart)
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Interview Highlights", h2))
    story.append(Paragraph(f"<b>Best moment:</b> {report.interview_highlights.best_answer}", body))
    story.append(Paragraph(f"<b>Concern:</b> {report.interview_highlights.concern_answer}", body))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Suggested Next Steps", h2))
    story.append(Paragraph(report.suggested_next_steps, body))
    story.append(Spacer(1, 0.1 * inch))

    if report.red_flags:
        story.append(Paragraph("Red Flags", h2))
        for flag in report.red_flags:
            story.append(Paragraph(f"⚠ {flag}", small))

    doc.build(story)
    return buffer.getvalue()
