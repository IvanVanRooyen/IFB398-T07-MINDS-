import datetime
import math

import openpyxl
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.db import transaction

from core.geo_utils import parse_grid_epsg, projected_to_wgs84
from core.models import AssayResult, Drillhole, DrillholeSurvey, LithologyInterval, Process

from .instrument import instrument


def _str(val):
    if val is None:
        return ""
    s = str(val).strip()
    return s if s.lower() not in ("none", "nan") else ""


def _float(val):
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        raise ValueError("Expected a number, not a boolean")
    try:
        result = float(val)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid number: {val!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"Number must be finite: {val!r}")
    return result


def _date(val):
    if val is None or val == "":
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    raise ValueError(f"Expected an Excel date: {val!r}")


def _int(val):
    number = _float(val)
    if number is None:
        return None
    if not number.is_integer():
        raise ValueError(f"Expected an integer: {val!r}")
    return int(number)


@instrument
def _build_hmap(header_row):
    """
    Build a lowercase header->column-index map from the first row of a sheet.
    Duplicate headers (e.g. two 'Mineralisation' columns) get a #2, #3 suffix
    on the later occurrences so both are reachable.
    """
    hmap = {}
    seen = {}
    for idx, val in enumerate(header_row):
        if val is None:
            continue
        key = str(val).strip().lower()
        if key in seen:
            seen[key] += 1
            hmap[f"{key}#{seen[key]}"] = idx
        else:
            seen[key] = 1
            hmap[key] = idx
    return hmap


@instrument
def _h(row, hmap, key, default=None):
    """Retrieve a cell value by header name (case-insensitive)."""
    idx = hmap.get(key.lower())
    if idx is not None and idx < len(row):
        return row[idx]
    return default


CHILD_SHEETS = [
    (
        DrillholeSurvey,
        "DH DHSurvey",
        "surveys",
        ("holeid", "depth"),
        [
            ("depth", "depth", True),
            ("dip", "dip", True),
            ("azimuth_tn", "azimuth (tn)", True),
            ("azimuth_mag", "azimuth_mag", True),
            ("comment", "azi comment", False),
        ],
    ),
    (
        LithologyInterval,
        "DH_Lithology",
        "litho",
        ("holeid", "from", "to"),
        [
            ("from_depth", "from", True),
            ("to_depth", "to", True),
            ("lithology", "lithology", False),
            ("description", "description", False),
            ("mineralisation", "mineralisation", False),
            ("hardness", "hardness", False),
            ("weathering", "weathering", False),
            ("acid_reaction", "acid", False),
            ("colour", "colour", False),
            ("oxidation", "oxidation", False),
            ("mineralisation_b", "mineralisation#2", False),
            ("mineralisation_2", "mineralisation 2", False),
            ("alteration", "alteration", False),
            ("alteration_2", "alteration 2", False),
            ("veins", "veins", False),
            ("recovery_pct", "recovery %", False),
            ("core_size", "core size", False),
        ],
    ),
    (
        AssayResult,
        "DH_Assays",
        "assay",
        ("holeid", "from", "to"),
        [
            ("from_depth", "from", True),
            ("to_depth", "to", True),
            ("lab_batch_number", "lab batch number", False),
            ("sample_number", "samplenumber", False),
            ("comment", "comment", False),
            ("au_ppm", "au_ppm", True),
            ("au_ppm_check1", "au_ppmchecks", True),
            ("au_ppm_check2", "au_ppmchecks2", True),
            ("cu_ppm", "cu_ppm", True),
            ("pb_ppm", "pb_ppm", True),
            ("zn_ppm", "zn_ppm", True),
            ("ag_ppm", "ag_ppm", True),
            ("as_ppm", "as_ppm", True),
            ("bi_ppm", "bi_ppm", True),
            ("cd_ppm", "cd_ppm", True),
            ("sb_ppm", "sb_ppm", True),
            ("mn_ppm", "mn_ppm", True),
            ("mo_ppm", "mo_ppm", True),
            ("pt_ppb", "pt_ppb", True),
            ("pd_ppb", "pd_ppb", True),
            ("laboratory", "laboratory", False),
            ("au_method", "au_method", False),
            ("cu_method", "cu_method", False),
            ("cu_method_2", "cu_method2", False),
            ("pb_method", "pb_method", False),
            ("zn_method", "zn_method", False),
            ("ag_method", "ag_method", False),
            ("as_method", "as_method", False),
            ("bi_method", "bi_method", False),
            ("cd_method", "cd_method", False),
            ("sb_method", "sb_method", False),
            ("mn_method", "mn_method", False),
            ("mo_method", "mo_method", False),
            ("pt_method", "pt_method", False),
            ("pd_method", "pd_method", False),
        ],
    ),
]


def _range(value, label, low, high=None):
    if value is not None and (value < low or (high is not None and value > high)):
        raise ValueError(
            f"{label} must be between {low} and {high if high is not None else 'the hole depth'}"
        )


def _rows(wb, sheet, required):
    if sheet not in wb.sheetnames:
        raise ValueError(f"Missing sheet: {sheet}")
    rows = wb[sheet].iter_rows(values_only=True)
    hmap = _build_hmap(next(rows, ()))
    missing = set(required) - hmap.keys()
    if missing:
        raise ValueError(f"{sheet}: missing headers: {', '.join(sorted(missing))}")
    return hmap, [
        (i, row) for i, row in enumerate(rows, 2) if any(v is not None and v != "" for v in row)
    ]


@instrument
def run_drillhole_import(file_obj, org, process, dry_run=False, update=False, warn=None):
    """Validate a complete workbook, then atomically apply it to one process.

    Existing holes are entirely skipped unless update=True. Updating replaces all
    survey/lithology/assay rows for the workbook's holes, including empty sheets.
    Errors reject the whole workbook; dry runs perform the same validation but
    report planned counts without writing. The process lock serializes imports.
    """
    if not org.pk or process.organisation_id != org.pk:
        raise ValueError("Process must belong to the selected organisation.")
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    try:
        # Check every sheet before considering any writes.
        sheets = {"DH Collars": _rows(wb, "DH Collars", ("holeid",))}
        for _, sheet, _, required, _ in CHILD_SHEETS:
            sheets[sheet] = _rows(wb, sheet, required)
    finally:
        wb.close()

    counters = {
        f"{prefix}_{suffix}": 0
        for prefix in ("collars", "surveys", "litho", "assay")
        for suffix in ("created", "errors")
    }
    counters.update(collars_updated=0, collars_skipped=0)
    errors = []

    def reject(prefix, sheet, row, exc):
        message = f"{sheet} row {row}: {exc}"
        errors.append(message)
        counters[f"{prefix}_errors"] += 1
        if warn:
            warn(message)

    with transaction.atomic():
        locked_process = Process.objects.select_for_update().get(pk=process.pk)
        if locked_process.organisation_id != org.pk:
            raise ValueError("Process must belong to the selected organisation.")
        holes = {}
        seen = set()
        hmap, rows = sheets["DH Collars"]
        for row_idx, row in rows:
            try:
                holeid = _str(_h(row, hmap, "holeid"))
                if not holeid:
                    raise ValueError("Missing HOLEID")
                if holeid in seen:
                    raise ValueError(f"Duplicate HOLEID: {holeid}")
                seen.add(holeid)
                grid_str = _str(_h(row, hmap, "grid"))
                raw_east = _float(_h(row, hmap, "mga94_east"))
                raw_north = _float(_h(row, hmap, "mga94_north"))
                collar_point, source_crs = None, ""
                if (raw_east is None) != (raw_north is None):
                    raise ValueError("Easting and northing must be supplied together")
                if raw_east is not None:
                    epsg = parse_grid_epsg(grid_str)
                    if epsg is None:
                        raise ValueError(f"Unsupported GRID: {grid_str!r}")
                    lon, lat = projected_to_wgs84(raw_east, raw_north, epsg)
                    collar_point, source_crs = Point(lon, lat, srid=4326), f"EPSG:{epsg}"
                drill_type = _str(_h(row, hmap, "type")).upper()
                defaults = dict(
                    drill_type=drill_type,
                    company=_str(_h(row, hmap, "company")),
                    drill_company=_str(_h(row, hmap, "drill company")),
                    current_epm=_str(_h(row, hmap, "current_epm")),
                    original_epm=_str(_h(row, hmap, "original epm")),
                    year_report=_int(_h(row, hmap, "year report")),
                    company_report=_str(_h(row, hmap, "companyreport")),
                    collar_location=collar_point,
                    elevation=_float(_h(row, hmap, "elevation")),
                    depth=_float(_h(row, hmap, "total_depth")),
                    dip=_float(_h(row, hmap, "dip")),
                    azimuth=_float(_h(row, hmap, "azimuth (tn)")),
                    date_commenced=_date(_h(row, hmap, "date commenced")),
                    date_completed=_date(_h(row, hmap, "date completed")),
                    hole_id_original=_str(_h(row, hmap, "holeid_original")),
                    comments=_str(_h(row, hmap, "comments")),
                    source_crs=source_crs,
                    source_easting=raw_east,
                    source_northing=raw_north,
                    organisation=org,
                    process=process,
                )
                candidate = Drillhole(name=holeid, **defaults)
                candidate.full_clean()
                _range(candidate.depth, "Total depth", 0)
                _range(candidate.dip, "Dip", -90, 90)
                _range(candidate.azimuth, "Azimuth", 0, 360)
                if (
                    candidate.date_commenced
                    and candidate.date_completed
                    and candidate.date_completed < candidate.date_commenced
                ):
                    raise ValueError("Completion date precedes commencement")
                matches = list(
                    Drillhole.objects.filter(name=holeid, organisation=org, process=locked_process)
                )
                if len(matches) > 1:
                    raise ValueError(
                        f"Ambiguous existing HOLEID: {holeid}; resolve duplicates first"
                    )
                existing = matches[0] if matches else None
                holes[holeid] = (candidate, existing, defaults)
            except (ValueError, ValidationError) as exc:
                reject("collars", "DH Collars", row_idx, exc)

        children = []
        for model, sheet, prefix, _, fields in CHILD_SHEETS:
            hmap, rows = sheets[sheet]
            for row_idx, row in rows:
                try:
                    holeid = _str(_h(row, hmap, "holeid"))
                    if holeid not in holes:
                        raise ValueError(f"Unknown or invalid HOLEID: {holeid!r}")
                    candidate, _, _ = holes[holeid]
                    values = {
                        field: (_float if numeric else _str)(_h(row, hmap, header))
                        for field, header, numeric in fields
                    }
                    child = model(drillhole=candidate, **values)
                    child.full_clean(exclude=["drillhole"])
                    end = values.get("depth", values.get("to_depth"))
                    _range(end, "Depth", 0, candidate.depth)
                    if "from_depth" in values:
                        _range(values["from_depth"], "From depth", 0)
                        if values["from_depth"] >= end:
                            raise ValueError("Interval requires from < to")
                    _range(values.get("dip"), "Dip", -90, 90)
                    for field in ("azimuth_tn", "azimuth_mag"):
                        _range(values.get(field), field, 0, 360)
                    children.append((prefix, holeid, child))
                except (ValueError, ValidationError) as exc:
                    reject(prefix, sheet, row_idx, exc)

        if errors:
            return {"counters": counters, "errors": errors, "valid": False, "applied": False}

        targets = {}
        for holeid, (candidate, existing, defaults) in holes.items():
            if existing and not update:
                counters["collars_skipped"] += 1
                continue
            counters["collars_updated" if existing else "collars_created"] += 1
            targets[holeid] = existing or candidate
            if not dry_run:
                if existing:
                    for field, value in defaults.items():
                        setattr(existing, field, value)
                    existing.save()
                    for model, *_ in CHILD_SHEETS:
                        model.objects.filter(drillhole=existing).delete()
                else:
                    candidate.save()
        for prefix, holeid, child in children:
            if holeid in targets:
                counters[f"{prefix}_created"] += 1
                if not dry_run:
                    child.drillhole = targets[holeid]
                    child.save()
    return {"counters": counters, "errors": [], "valid": True, "applied": not dry_run}
