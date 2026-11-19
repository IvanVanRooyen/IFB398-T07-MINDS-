"""Bounded, deterministic geological evidence captured into a report revision."""

import hashlib
import json
import math
from io import BytesIO

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw
from reportlab.graphics.shapes import Circle, Drawing, Line, String
from reportlab.lib.colors import HexColor

from core.access import require_record_access
from core.models import AssayResult, Drillhole, LithologyInterval

MAX_HOLES = 20
MAX_ROWS = 100
TABLES = [
    ("collars", "Drillhole collars"),
    ("assays", "Assay intervals (Au and Cu)"),
    ("lithology", "Lithology intervals"),
]
NOTE = (
    "Database snapshot; recorded values have not been independently verified. "
    "Depths are metres down hole, not true widths. Au and Cu assays are ppm. "
    "BDL preserves the negative source notation; no detection threshold is inferred. "
    "Missing values are shown as —. No resource estimate or compliance certification is implied."
)
PLAN_NOTE = (
    "Collar locations from the saved WGS84 snapshot; north is up. "
    "Local schematic with longitude adjusted at the mean latitude; no basemap, "
    "survey accuracy or distance measurement. Labels identify rows in the collar key."
)


class AppendixForm(forms.Form):
    appendix_action = forms.ChoiceField(
        choices=[
            ("preserve", "Keep saved appendix"),
            ("replace", "Capture current database records"),
            ("remove", "Remove appendix"),
        ],
        required=False,
    )
    appendix_tables = forms.MultipleChoiceField(choices=TABLES, required=False)
    appendix_plan = forms.BooleanField(required=False)

    def clean(self):
        data = super().clean()
        if data.get("appendix_action") == "replace" and not (
            data.get("appendix_tables") or data.get("appendix_plan")
        ):
            raise ValidationError(
                "Choose at least one table or the collar plan before capturing records."
            )
        return data


def from_post(data, user, report):
    form = AppendixForm(data)
    if not form.is_valid():
        raise ValidationError(
            [message for messages in form.errors.values() for message in messages]
        )
    action = form.cleaned_data.get("appendix_action") or "preserve"
    if action == "preserve":
        return report.data_appendix
    if action == "remove":
        return {}
    return capture(
        user,
        report.process,
        report.prospect,
        form.cleaned_data["appendix_tables"],
        form.cleaned_data["appendix_plan"],
    )


def number(value, low=None, high=None):
    if value is None:
        return "—"
    if (
        not math.isfinite(value)
        or (low is not None and value < low)
        or (high is not None and value > high)
    ):
        raise ValidationError(
            "Stored geological measurements are invalid. Correct them before capturing an appendix."
        )
    return format(value, ".15g")


def _interval(record):
    start = number(record.from_depth, 0)
    end = number(record.to_depth, 0, record.drillhole.depth)
    if record.to_depth <= record.from_depth:
        raise ValidationError(
            "Stored intervals must end after they start. Correct them before capturing an appendix."
        )
    return [start, end]


def _row(record, hole, cells):
    return {
        "id": str(record.pk),
        "hole_id": str(hole.pk),
        "url": reverse("drillhole_detail", args=[hole.pk]),
        "cells": cells,
    }


def capture(user, process, prospect, tables, plan):
    if process is None:
        raise ValidationError("Link this report to a project before capturing geological records.")
    require_record_access(user, process)
    if prospect:
        require_record_access(user, prospect)
        if prospect.process_id != process.pk or prospect.organisation_id != process.organisation_id:
            raise ValidationError(
                "The report prospect must belong to its project and organisation."
            )
    if set(tables) - {key for key, _ in TABLES}:
        raise ValidationError("Unknown appendix table.")
    holes = Drillhole.objects.filter(process=process, organisation=process.organisation)
    if prospect:
        holes = holes.filter(prospect=prospect)
    holes = list(holes.order_by("name", "pk")[: MAX_HOLES + 1])
    if len(holes) > MAX_HOLES:
        raise ValidationError(
            f"This scope exceeds {MAX_HOLES} drillholes. Link the report to a smaller prospect before capture."
        )
    result = {
        "schema_version": 1,
        "captured_at": timezone.now().isoformat(),
        "scope": {
            "project_id": str(process.pk),
            "project": process.name,
            "prospect_id": str(prospect.pk) if prospect else None,
            "prospect": prospect.name if prospect else None,
        },
        "options": {"tables": sorted(tables), "plan": bool(plan)},
        "note": NOTE,
        "tables": [],
        "plan": None,
    }
    collar_rows = []
    points = []
    for index, hole in enumerate(holes, 1):
        lon = lat = None
        if hole.collar_location:
            lon, lat = hole.collar_location.x, hole.collar_location.y
            number(lon, -180, 180)
            number(lat, -90, 90)
            points.append({"label": str(index), "longitude": lon, "latitude": lat})
        collar_rows.append(
            _row(
                hole,
                hole,
                [
                    str(index),
                    hole.name,
                    number(lon),
                    number(lat),
                    number(hole.depth, 0),
                    number(hole.dip, -90, 90),
                    number(hole.azimuth, 0, 360),
                ],
            )
        )
    if "collars" in tables:
        result["tables"].append(
            {
                "kind": "collars",
                "title": "Drillhole collars",
                "columns": [
                    "Key",
                    "Drillhole",
                    "Longitude (°E)",
                    "Latitude (°N)",
                    "Depth (m)",
                    "Dip (°)",
                    "Bearing (°TN)",
                ],
                "rows": collar_rows,
            }
        )
    if "assays" in tables:
        records = list(
            AssayResult.objects.filter(drillhole__in=holes)
            .select_related("drillhole")
            .order_by("drillhole__name", "drillhole_id", "from_depth", "to_depth", "pk")[
                : MAX_ROWS + 1
            ]
        )
        if len(records) > MAX_ROWS:
            raise ValidationError(
                f"Assay table exceeds {MAX_ROWS} rows. Use a smaller prospect or omit this table."
            )
        rows = []
        for record in records:
            values = []
            for value in (record.au_ppm, record.cu_ppm):
                text = number(value)
                values.append(f"BDL ({text})" if value is not None and value < 0 else text)
            rows.append(
                _row(
                    record,
                    record.drillhole,
                    [record.drillhole.name, *_interval(record), record.sample_number, *values],
                )
            )
        result["tables"].append(
            {
                "kind": "assays",
                "title": "Assay intervals — recorded Au and Cu",
                "columns": ["Drillhole", "From (m)", "To (m)", "Sample", "Au (ppm)", "Cu (ppm)"],
                "rows": rows,
            }
        )
    if "lithology" in tables:
        records = list(
            LithologyInterval.objects.filter(drillhole__in=holes)
            .select_related("drillhole")
            .order_by("drillhole__name", "drillhole_id", "from_depth", "to_depth", "pk")[
                : MAX_ROWS + 1
            ]
        )
        if len(records) > MAX_ROWS:
            raise ValidationError(
                f"Lithology table exceeds {MAX_ROWS} rows. Use a smaller prospect or omit this table."
            )
        rows = [
            _row(r, r.drillhole, [r.drillhole.name, *_interval(r), r.lithology, r.mineralisation])
            for r in records
        ]
        result["tables"].append(
            {
                "kind": "lithology",
                "title": "Lithology intervals",
                "columns": ["Drillhole", "From (m)", "To (m)", "Lithology", "Mineralisation"],
                "rows": rows,
            }
        )
    if plan:
        if (
            points
            and max(p["longitude"] for p in points) - min(p["longitude"] for p in points) > 180
        ):
            raise ValidationError(
                "This scope crosses the date line. Omit the schematic plan and use the coordinate table."
            )
        result["plan"] = {
            "title": "Drillhole collar plan",
            "note": PLAN_NOTE,
            "points": points,
            "key": collar_rows,
            "omitted": len(holes) - len(points),
        }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return result


def layout(plan):
    points = plan["points"]
    if not points:
        return []
    mean_lat = sum(p["latitude"] for p in points) / len(points)
    scale = max(math.cos(math.radians(mean_lat)), 0.000001)
    xs = [p["longitude"] * scale for p in points]
    ys = [p["latitude"] for p in points]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), 0.0001)
    grouped = {}
    for p, x, y in zip(points, xs, ys):
        key = (x, y)
        if key in grouped:
            grouped[key]["label"] += "," + p["label"]
        else:
            grouped[key] = {
                "label": p["label"],
                "x": round(300 + (x - cx) * 240 / span, 3),
                "y": round(165 - (y - cy) * 240 / span, 3),
            }
    return list(grouped.values())


def presentation(snapshot):
    return {
        "snapshot": snapshot,
        "plot_points": layout(snapshot["plan"]) if snapshot and snapshot.get("plan") else [],
    }


def drawing(plan):
    d = Drawing(600, 330)
    d.add(String(560, 305, "N", fontSize=12))
    d.add(Line(564, 275, 564, 295))
    d.add(Line(564, 295, 560, 287))
    d.add(Line(564, 295, 568, 287))
    for point in layout(plan):
        x, y = point["x"], 330 - point["y"]
        d.add(Circle(x, y, 4, fillColor=HexColor("#0e7490")))
        d.add(String(x + 7, y + 4, point["label"], fontSize=11))
    return d


def png(plan):
    image = Image.new("RGB", (1200, 660), "white")
    draw = ImageDraw.Draw(image)
    draw.text((1120, 40), "N", fill="black")
    draw.line((1128, 110, 1128, 70), fill="black", width=3)
    draw.line((1128, 70, 1118, 86), fill="black", width=3)
    draw.line((1128, 70, 1138, 86), fill="black", width=3)
    for p in layout(plan):
        x, y = p["x"] * 2, p["y"] * 2
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill="#0e7490")
        draw.text((x + 14, y - 16), p["label"], fill="black", font_size=22)
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf
