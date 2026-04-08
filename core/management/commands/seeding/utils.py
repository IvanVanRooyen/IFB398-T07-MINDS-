import hashlib
import os
import random

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from faker import Faker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import constants
from .pdf_generator import (
    compliance_content,
    environmental_content,
    internal_content,
    jorc_content,
    technical_content,
    valmin_content,
)

fake = Faker()
User = get_user_model()

DOCTYPE_FUNCTION_MAP = {
    "JORC": jorc_content,
    "VALMIN": valmin_content,
    "TECHNICAL": technical_content,
    "ENVIRONMENTAL": environmental_content,
    "COMPLIANCE": compliance_content,
    "INTERNAL": internal_content,
}


def generate_pdf(doc_type, org, process, commodity, output_path):
    generator = DOCTYPE_FUNCTION_MAP.get(doc_type, internal_content)
    title, sections = generator(org, process, commodity or "Gold")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            spaceAfter=6 * mm,
            spaceBefore=10 * mm,
        )
    )

    story = []

    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(f"Prepared for: {org.name}", styles["Normal"]))
    story.append(Paragraph(f"Project: {process.name}", styles["Normal"]))
    story.append(
        Paragraph(
            f"Date: {fake.date_this_year().strftime('%d %B %Y')}", styles["Normal"]
        )
    )
    story.append(
        Paragraph(
            f"Classification: {random.choice(constants.CONFIDENTIALITY_LEVELS)}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 20 * mm))

    meta_data = [
        ["Document Type", doc_type],
        ["Commodity", commodity or "N/A"],
        ["Organisation", org.name or "N/A"],
        ["Project / Operation", process.name or "N/A"],
        ["Prepared By", fake.name()],
        ["Reviewed By", fake.name()],
    ]
    meta_table = Table(meta_data, colWidths=[55 * mm, 100 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8e8e8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 30 * mm))

    for heading, paragraphs in sections:
        story.append(Paragraph(heading, styles["SectionHeading"]))
        for para_text in paragraphs:
            story.append(Paragraph(para_text, styles["Normal"]))
            story.append(Spacer(1, 3 * mm))

    doc.build(story)
    return file_sha256(str(output_path))


def random_point():
    lat = random.uniform(*constants.AU_LAT_RANGE)
    lon = random.uniform(*constants.AU_LON_RANGE)

    return Point(lon, lat, srid=4326)


def random_multipolygon():
    cy = random.uniform(*constants.AU_LAT_RANGE)
    cx = random.uniform(*constants.AU_LON_RANGE)
    d = 0.05

    p = Polygon(
        (
            (cx - d, cy - d),
            (cx + d, cy - d),
            (cx + d, cy + d),
            (cx - d, cy + d),
            (cx - d, cy - d),
        ),
        srid=4326,
    )

    return MultiPolygon(p, srid=4326)


def file_sha256(path: str) -> str:
    """Compute SHA-256 of file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fake_sha256():
    return hashlib.sha256(fake.binary(length=64)).hexdigest()
