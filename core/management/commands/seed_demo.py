"""Small synthetic exploration scenario, restricted to explicit local settings."""

import hashlib
import io
import logging
import os
import uuid
from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from docx import Document as WordDocument

from core.ai.composition import ReportCompositionForm, compose_report
from core.models import (
    ApprovalWorkflow,
    AssayResult,
    AuditLog,
    DocLink,
    Document,
    DocumentChunk,
    Drillhole,
    DrillholeSurvey,
    LithologyInterval,
    Organisation,
    Process,
    Prospect,
    SavedReport,
    Tenement,
    log_audit,
)
from core.reporting.appendix import capture

log = logging.getLogger(__name__)
WRITER = "demo-geologist"
REVIEWER = "demo-reviewer"


def identity(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://example.invalid/minds/synthetic-v1/{name}")


def remove_files(names):
    for name in names:
        try:
            default_storage.delete(name)
        except Exception:
            log.exception("Could not clean up a synthetic dataset file")


class Command(BaseCommand):
    help = "Create a synthetic local exploration scenario; repeat runs preserve existing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Replace only the named synthetic project and its records; keep users and other projects.",
        )

    def handle(self, *args, **options):
        if (
            not settings.DEBUG
            or not getattr(settings, "ALLOW_DEMO_SEED", False)
            or settings.DOCUMENT_STORAGE != "filesystem"
        ):
            raise CommandError(
                "Demo seeding requires the local development profile and filesystem storage."
            )
        password = os.environ.get("DEMO_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set DEMO_PASSWORD to at least 12 characters before seeding.")
        created_files = []
        try:
            with transaction.atomic():
                org, _ = Organisation.objects.get_or_create(
                    pk=identity("organisation"), defaults={"name": "MINDS Synthetic Exploration"}
                )
                # Serialise seed/reset operations, including the first project creation.
                org = Organisation.objects.select_for_update().get(pk=org.pk)
                people = []
                for username, role in [(WRITER, "GEOLOGIST_EXPL"), (REVIEWER, "COMPETENT_PERSON")]:
                    user, made = User.objects.get_or_create(username=username)
                    if not made and (
                        user.is_staff or user.is_superuser or user.profile.organisation_id != org.pk
                    ):
                        raise CommandError(
                            f"The username {username} belongs to another account; no data was changed."
                        )
                    if made:
                        user.set_password(password)
                        user.save()
                        user.profile.organisation = org
                        user.profile.role = role
                        user.profile.clearance_level = (
                            "JORC_APPROVED" if username == REVIEWER else "CONFIDENTIAL"
                        )
                        user.profile.can_approve_jorc = username == REVIEWER
                        user.profile.can_approve_valmin = username == REVIEWER
                        user.profile.save()
                    people.append(user)
                writer, _reviewer = people
                old = Process.objects.filter(pk=identity("project")).first()
                if old and old.organisation_id != org.pk:
                    raise CommandError(
                        "Synthetic project identity is already in use by another organisation."
                    )
                if options["reset"] and old:
                    docs = Document.objects.filter(process=old)
                    old_names = [name for name in docs.values_list("file", flat=True) if name]
                    reports = SavedReport.objects.filter(process=old)
                    ApprovalWorkflow.objects.filter(
                        content_type=ContentType.objects.get_for_model(SavedReport),
                        object_id__in=reports.values("pk"),
                    ).delete()
                    reports.delete()
                    docs.delete()
                    old.delete()
                    transaction.on_commit(lambda names=old_names: remove_files(names))
                project, _ = Process.objects.get_or_create(
                    pk=identity("project"),
                    defaults={
                        "name": "Red Ridge — synthetic copper project",
                        "organisation": org,
                        "commodity": "Copper",
                        "geom": MultiPolygon(
                            Polygon(
                                (
                                    (152.99, -27.01),
                                    (153.02, -27.01),
                                    (153.02, -26.98),
                                    (152.99, -26.98),
                                    (152.99, -27.01),
                                ),
                                srid=4326,
                            ),
                            srid=4326,
                        ),
                    },
                )
                prospect, _ = Prospect.objects.get_or_create(
                    pk=identity("prospect"),
                    defaults={
                        "name": "Northern structure — synthetic target",
                        "organisation": org,
                        "process": project,
                        "geom": Point(153, -27, srid=4326),
                        "hypothesis": "Copper may follow the interpreted northern structure. This is an unverified hypothesis.",
                        "objective": "Compare recorded intervals and plan follow-up sampling; identify missing evidence.",
                    },
                )
                if prospect.organisation_id != org.pk or prospect.process_id != project.pk:
                    raise CommandError("Synthetic prospect identity belongs to a different scope.")
                tenement, _ = Tenement.objects.get_or_create(
                    pk=identity("tenement"),
                    defaults={
                        "name": "Synthetic permit area",
                        "organisation": org,
                        "process": project,
                        "geom": project.geom,
                    },
                )
                if tenement.organisation_id != org.pk or tenement.process_id != project.pk:
                    raise CommandError("Synthetic tenement identity belongs to a different scope.")
                for index, (longitude, latitude, depth) in enumerate(
                    [(153, -27, 100), (153.004, -26.997, 140), (None, None, 80)], 1
                ):
                    hole, _ = Drillhole.objects.get_or_create(
                        pk=identity(f"hole-{index}"),
                        defaults={
                            "name": f"RR-{index:02}",
                            "organisation": org,
                            "process": project,
                            "prospect": prospect,
                            "collar_location": Point(longitude, latitude, srid=4326)
                            if longitude is not None
                            else None,
                            "depth": depth,
                            "dip": -60,
                            "azimuth": 45,
                            "drill_type": "DDH",
                            "comments": "Synthetic data. RR-03 intentionally has no collar coordinates.",
                        },
                    )
                    if hole.organisation_id != org.pk or hole.process_id != project.pk:
                        raise CommandError(
                            "Synthetic drillhole identity belongs to a different scope."
                        )
                    DrillholeSurvey.objects.get_or_create(
                        pk=identity(f"survey-{index}"),
                        defaults={"drillhole": hole, "depth": 10, "dip": -60, "azimuth_tn": 45},
                    )
                    LithologyInterval.objects.get_or_create(
                        pk=identity(f"lithology-{index}"),
                        defaults={
                            "drillhole": hole,
                            "from_depth": 0,
                            "to_depth": 20,
                            "lithology": "Basalt",
                            "mineralisation": "Chalcopyrite",
                        },
                    )
                    AssayResult.objects.get_or_create(
                        pk=identity(f"assay-{index}"),
                        defaults={
                            "drillhole": hole,
                            "from_depth": 10,
                            "to_depth": 12,
                            "sample_number": f"SYN-{index:02}",
                            "au_ppm": -0.01,
                            "cu_ppm": 8000 if index == 1 else 1200,
                        },
                    )
                doc = Document.objects.filter(pk=identity("document")).first()
                if doc is None:
                    text = (
                        "Synthetic field record, not client or field data. RR-01 recorded 8000 ppm Cu from 10 to 12 m. "
                        "The negative Au value -0.01 retains below-detection source notation. "
                        "RR-03 has no mapped collar. No resource estimate, geological finding or compliance certification is established."
                    )
                    word = WordDocument()
                    word.add_heading("Synthetic Red Ridge field record", level=1)
                    word.add_paragraph(text)
                    blob = io.BytesIO()
                    word.save(blob)
                    raw = blob.getvalue()
                    doc = Document(
                        id=identity("document"),
                        title="Synthetic field record",
                        organisation=org,
                        process=project,
                        confidentiality="internal",
                        created_by=writer,
                        timestamp=date(2026, 1, 15),
                        doc_type="Field record",
                        extracted_text=text,
                        checksum_sha256=hashlib.sha256(raw).hexdigest(),
                    )
                    doc.file.save("synthetic-field-record.docx", ContentFile(raw), save=False)
                    created_files.append(doc.file.name)
                    doc.save()
                    DocumentChunk.objects.create(
                        document=doc,
                        process=project,
                        chunk_index=0,
                        text=text,
                        doc_type=doc.doc_type,
                        timestamp=doc.timestamp,
                    )
                if doc.organisation_id != org.pk or doc.process_id != project.pk:
                    raise CommandError("Synthetic document identity belongs to a different scope.")
                existing_report = SavedReport.objects.filter(pk=identity("report")).first()
                if existing_report and (
                    existing_report.organisation_id != org.pk
                    or existing_report.process_id != project.pk
                ):
                    raise CommandError("Synthetic report identity belongs to a different scope.")
                DocLink.objects.get_or_create(
                    document=doc,
                    content_type=ContentType.objects.get_for_model(Prospect),
                    object_id=prospect.pk,
                    defaults={"created_by": writer},
                )
                if not SavedReport.objects.filter(pk=identity("report")).exists():
                    form = ReportCompositionForm(
                        {
                            "composer_version": "1",
                            "drafting_mode": "manual",
                            "process_id": str(project.pk),
                            "report_type": "exploration",
                            "tone": "technical",
                            "source_mode": "selected",
                            "document_ids": [str(doc.pk)],
                            "include_references": "on",
                            "include_findings": "on",
                        },
                        user=writer,
                        prospect=prospect,
                    )
                    if not form.is_valid():
                        raise CommandError(
                            "The existing demo data no longer supports a report. Review it or use --reset."
                        )
                    bundle = compose_report(form)
                    report = SavedReport.objects.create(
                        id=identity("report"),
                        title="Synthetic exploration evidence review",
                        organisation=org,
                        process=project,
                        prospect=prospect,
                        created_by=writer,
                        clearance_level="CONFIDENTIAL",
                        content_md=bundle["md"],
                        content_hash=hashlib.sha256(bundle["md"].encode()).hexdigest(),
                        generation_manifest=bundle["manifest"],
                        data_appendix=capture(
                            writer, project, prospect, ["collars", "assays", "lithology"], True
                        ),
                    )
                    report.source_documents.set([doc])
                    log_audit(
                        writer, AuditLog.ActionType.CREATE, report, "Created synthetic demo report"
                    )
        except Exception:
            remove_files(created_files)
            raise
        self.stdout.write(
            self.style.SUCCESS(
                f"Synthetic project ready. Accounts: {WRITER}, {REVIEWER}. Existing passwords were preserved; new accounts use DEMO_PASSWORD."
            )
        )
