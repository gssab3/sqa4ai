'''
This Python file is required to generate the PDF containing the "text_single_numbered" security requirements.
'''

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER


def export_requirement_pdf(output_path: str, corpus: str, title: str = "Security Requirements Generated (GEN1+GEN2)"):
    """
    Create a PDF with a centered title and selectable/copyable body text.
    - output_path: path to the generated PDF (e.g. 'requirements_llm.pdf')
    - corpus: string with numbered requirements separated by newlines
    - title: title displayed at the top of the PDF
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=title,
        author="RAG System"
    )

    styles = getSampleStyleSheet()

    # Title style
    title_style = ParagraphStyle(
        name="TitleCentered",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=12
    )

    # Body style
    body_style = ParagraphStyle(
        name="BodyJustified",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        spaceAfter=6
    )

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5*cm))

    # Convert corpus lines to separate paragraphs
    for line in corpus.splitlines():
        if line.strip():
            # Escape characters that may break reportlab parser
            safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_line, body_style))

    doc.build(story)