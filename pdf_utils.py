'''
Questo file python è necessario per la generazione del pdf contenente i requisiti di sicurezza del "testo_unico_numerato"
'''

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER

def export_requisiti_pdf(output_path: str, testo_unico_numerato: str, titolo: str = "Requisiti Generati dall'LLM"):
    """
    Crea un PDF con un titolo e un corpo testuale selezionabile/copiabile.
    - output_path: percorso del PDF (es. 'requisiti_llm.pdf')
    - testo_unico_numerato: stringa con i requisiti numerati separati da \n
    - titolo: titolo in cima al PDF
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=titolo,
        author="Pipeline RAG"
    )

    styles = getSampleStyleSheet()

    # Stile del titolo
    title_style = ParagraphStyle(
        name="TitleCentered",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=12
    )

    # Stile del corpo
    body_style = ParagraphStyle(
        name="BodyJustified",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        spaceAfter=6
    )

    story = []
    story.append(Paragraph(titolo, title_style))
    story.append(Spacer(1, 0.5*cm))

    # Converti le righe del testo unico in paragrafi separati
    for line in testo_unico_numerato.splitlines():
        if line.strip():
            # Sostituisci i caratteri speciali che potrebbero rompere il parser di reportlab
            safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_line, body_style))

    doc.build(story)
