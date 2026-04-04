import csv
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_RATING_COLOR = {
    "Very Good": colors.HexColor("#166534"),
    "Good": colors.HexColor("#1d4ed8"),
    "Average": colors.HexColor("#854d0e"),
    "Low": colors.HexColor("#991b1b"),
}
_RATING_BG = {
    "Very Good": colors.HexColor("#dcfce7"),
    "Good": colors.HexColor("#dbeafe"),
    "Average": colors.HexColor("#fef9c3"),
    "Low": colors.HexColor("#fee2e2"),
}
_STATUS_COLOR = {
    "Select": "#166534",
    "Above Average": "#1d4ed8",
    "Reject": "#991b1b",
    "Strong Reject": "#7f1d1d",
    "On Hold": "#854d0e",
}


def record_to_pdf(record: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("rpt_title", parent=base["Title"], fontSize=22, textColor=colors.HexColor("#111827"), spaceAfter=4, alignment=TA_CENTER),
        "subtitle": ParagraphStyle("rpt_subtitle", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#6b7280"), spaceAfter=12, alignment=TA_CENTER),
        "section": ParagraphStyle("rpt_section", parent=base["Normal"], fontSize=12, fontName="Helvetica-Bold", textColor=colors.HexColor("#1d4ed8"), spaceBefore=16, spaceAfter=8),
        "obs": ParagraphStyle("rpt_obs", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#374151"), leading=16, alignment=TA_LEFT),
        "skill": ParagraphStyle("rpt_skill", parent=base["Normal"], fontSize=9.5, textColor=colors.HexColor("#111827"), leading=13, wordWrap="CJK"),
        "rating": ParagraphStyle("rpt_rating", parent=base["Normal"], fontSize=9.5, textColor=colors.HexColor("#111827"), alignment=TA_CENTER),
    }
    status_color = colors.HexColor(_STATUS_COLOR.get(record["assessment_status"], "#374151"))
    page_width = A4[0] - 4*cm
    elems = []
    elems.append(Paragraph("Candidate Assessment Report", styles["title"]))
    elems.append(Paragraph(f"Generated on {datetime.now().strftime('%d %b %Y, %H:%M')}", styles["subtitle"]))
    elems.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb"), spaceAfter=12))
    elems.append(Paragraph("Interview Details", styles["section"]))
    # Keep width balanced so the table fits cleanly inside the page margins.
    meta_col_widths = [page_width * 0.18, page_width * 0.32, page_width * 0.2, page_width * 0.3]
    meta_data = [
        ["Candidate Name", record["candidate_name"], "Panel / Interviewer", record["panel_name"]],
        ["Date of Interview", _format_ddmmyyyy(record.get("date_of_interview")), "Assessment Status", record["assessment_status"]],
    ]
    meta_table = Table(meta_data, colWidths=meta_col_widths)
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f3f4f6")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#f3f4f6")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9.5),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (2,0), (2,-1), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (3,1), (3,1), status_color),
        ("FONTNAME", (3,1), (3,1), "Helvetica-Bold"),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("INNERGRID", (0,0), (-1,-1), 0.4, colors.HexColor("#e5e7eb")),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    elems.append(meta_table)
    skills = record.get("skills_assessment", {})
    if skills:
        elems.append(Paragraph("Skills Assessment", styles["section"]))
        skill_rows = [["Skill", "Rating"]] + [
            [Paragraph((s or "").strip(), styles["skill"]), Paragraph((r or "").strip(), styles["rating"])]
            for s, r in skills.items()
        ]
        skill_table = Table(skill_rows, colWidths=[page_width*0.7, page_width*0.3])
        ts = TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 10.5),
            ("ALIGN", (1,0), (1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
            ("INNERGRID", (0,0), (-1,-1), 0.4, colors.HexColor("#e5e7eb")),
            ("FONTSIZE", (0,1), (-1,-1), 9.5),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9fafb")]),
        ])
        for i, (_, rating) in enumerate(skills.items(), start=1):
            ts.add("BACKGROUND", (1,i), (1,i), _RATING_BG.get(rating, colors.HexColor("#f3f4f6")))
            ts.add("TEXTCOLOR", (1,i), (1,i), _RATING_COLOR.get(rating, colors.HexColor("#374151")))
            ts.add("FONTNAME", (1,i), (1,i), "Helvetica-Bold")
        skill_table.setStyle(ts)
        elems.append(skill_table)
    obs = (record.get("overall_observation") or "").strip()
    if obs:
        elems.append(Paragraph("Overall Observation", styles["section"]))
        obs_data = [[Paragraph(obs, styles["obs"])]]
        obs_table = Table(obs_data, colWidths=[page_width])
        obs_table.setStyle(TableStyle([
            ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
            ("LEFTPADDING", (0,0), (-1,-1), 14),
            ("RIGHTPADDING", (0,0), (-1,-1), 14),
            ("TOPPADDING", (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("LINEBEFORE", (0,0), (0,-1), 3, colors.HexColor("#1d4ed8")),
        ]))
        elems.append(obs_table)
    elems.append(Spacer(1, 0.5*cm))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e7eb")))
    elems.append(Paragraph("Resume &amp; Assessment Tool &middot; Powered by MeganSoft HRMS",
        ParagraphStyle("footer", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#9ca3af"), alignment=TA_CENTER, spaceBefore=6)))
    doc.build(elems)
    return buf.getvalue()


def records_to_csv(records: list) -> str:
    if not records:
        return ""
    all_skills = []
    seen = set()
    for r in records:
        for skill in r.get("skills_assessment", {}):
            if skill not in seen:
                all_skills.append(skill)
                seen.add(skill)
    base_fields = ["id", "candidate_name", "panel_name", "date_of_interview", "assessment_status", "overall_observation", "created_at"]
    fieldnames = base_fields + [f"skill_{s}" for s in all_skills]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        row = {
            "id": r["id"], "candidate_name": r["candidate_name"], "panel_name": r["panel_name"],
            "date_of_interview": _format_ddmmyyyy(r.get("date_of_interview")), "assessment_status": r["assessment_status"],
            "overall_observation": r.get("overall_observation", ""), "created_at": _format_ddmmyyyy(r.get("created_at")),
        }
        for skill in all_skills:
            row[f"skill_{skill}"] = r.get("skills_assessment", {}).get(skill, "")
        writer.writerow(row)
    return output.getvalue()


def _format_ddmmyyyy(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")

    raw = str(value).strip()
    if not raw:
        return ""

    if "T" in raw:
        raw = raw.split("T", 1)[0]
    elif " " in raw:
        raw = raw.split(" ", 1)[0]

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return str(value)


