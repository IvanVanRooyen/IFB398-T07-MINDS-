"""Render the saved geological snapshot without reading mutable project records."""

from html import escape

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from .appendix import drawing, png


def metadata(snapshot):
    scope = snapshot["scope"]
    return (
        f"Scope: {scope['project']}"
        + (f" / {scope['prospect']}" if scope["prospect"] else "")
        + f". Captured: {snapshot['captured_at']}. Snapshot SHA-256: {snapshot['sha256']}."
    )


def pdf_appendix(story, snapshot):
    if not snapshot:
        return
    styles = getSampleStyleSheet()
    cell = ParagraphStyle(
        "AppendixCell", parent=styles["Normal"], fontSize=8, leading=11, wordWrap="CJK"
    )

    def p(text):
        return Paragraph(escape(str(text)), cell)

    story.extend(
        [
            Spacer(1, 20),
            Paragraph("Geological evidence appendix", styles["Heading1"]),
            p(metadata(snapshot)),
            Spacer(1, 8),
            p(snapshot["note"]),
        ]
    )
    for block in snapshot["tables"]:
        story.extend([Spacer(1, 12), Paragraph(escape(block["title"]), styles["Heading2"])])
        if not block["rows"]:
            story.append(p("No records in the captured scope."))
            continue
        values = [[p(c) for c in block["columns"]]] + [
            [p(c) for c in r["cells"]] for r in block["rows"]
        ]
        table = Table(
            values,
            colWidths=[481 / len(block["columns"])] * len(block["columns"]),
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)
    plan = snapshot.get("plan")
    if plan:
        figure_block = [
            Spacer(1, 12),
            Paragraph(escape(plan["title"]), styles["Heading2"]),
            p(plan["note"]),
        ]
        if plan["points"]:
            figure = drawing(plan)
            figure.width = 480
            figure.height = 264
            figure.scale(0.8, 0.8)
            figure_block.append(figure)
            story.append(KeepTogether(figure_block))
            story.extend(
                p(f"{r['cells'][0]}: {r['cells'][1]} ({r['cells'][2]}, {r['cells'][3]})")
                for r in plan["key"]
            )
        else:
            story.append(
                KeepTogether(figure_block + [p("No mapped collars in the captured scope.")])
            )
        story.append(p(f"Collars without coordinates: {plan['omitted']}."))


def docx_appendix(doc, snapshot):
    if not snapshot:
        return
    doc.add_heading("Geological evidence appendix", level=1)
    doc.add_paragraph(metadata(snapshot))
    doc.add_paragraph(snapshot["note"])
    for block in snapshot["tables"]:
        doc.add_heading(block["title"], level=2)
        if not block["rows"]:
            doc.add_paragraph("No records in the captured scope.")
            continue
        table = doc.add_table(rows=1, cols=len(block["columns"]))
        table.style = "Table Grid"
        props = table.rows[0]._tr.get_or_add_trPr()
        repeat = OxmlElement("w:tblHeader")
        repeat.set(qn("w:val"), "true")
        props.append(repeat)
        for cell, text in zip(table.rows[0].cells, block["columns"]):
            cell.text = text
        for record in block["rows"]:
            for cell, text in zip(table.add_row().cells, record["cells"]):
                cell.text = str(text)
    plan = snapshot.get("plan")
    if plan:
        doc.add_heading(plan["title"], level=2)
        doc.add_paragraph(plan["note"]).paragraph_format.keep_with_next = True
        if plan["points"]:
            shape = doc.add_picture(png(plan), width=Inches(6))
            shape._inline.docPr.set("descr", plan["note"])
            for r in plan["key"]:
                doc.add_paragraph(
                    f"{r['cells'][0]}: {r['cells'][1]} ({r['cells'][2]}, {r['cells'][3]})"
                )
        else:
            doc.add_paragraph("No mapped collars in the captured scope.")
        doc.add_paragraph(f"Collars without coordinates: {plan['omitted']}.")
