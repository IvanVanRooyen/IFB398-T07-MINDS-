import random
import uuid
from datetime import timedelta
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from core.models import (
    ApprovalWorkflow,
    AuditLog,
    Document,
    DocumentView,
)

from .seeding import handlers
from .seeding.constants import (
    AUDIT_ACTIONS,
    COMMODITIES,
    MODEL_TYPES,
    NUM_APPROVAL_WORKFLOWS,
    NUM_AUDIT_LOGS,
    NUM_DOCUMENT_VIEWS,
    NUM_DOCUMENTS_PER_PROCESS,
    NUM_DRILLHOLES_PER_PROCESS,
    NUM_ORGANISATIONS,
    NUM_PROCESSES_PER_ORG,
    NUM_PROSPECTS_PER_PROCESS,
    NUM_TENEMENTS_PER_PROCESS,
    NUM_USERS_PER_ORG,
    ORG_MODES,
    PROCESS_MODES,
    WORKFLOW_STATUSES,
    WORKFLOW_TYPES,
)
from .seeding.utils import (
    User,
    fake,
)


class Command(BaseCommand):
    APP_LABEL = "core"
    FLUSH_MODELS = MODEL_TYPES

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", dest="flush", default=False)
        parser.add_argument(
            "--no-pdfs", action="store_false", dest="gen_pdf", default=True
        )

    def _log(self, msg):
        self.stdout.write(self.style.SUCCESS(f"{msg}"))

    def _get_s3_client(self):
        return handlers.get_s3_client()

    def _get_bucket(self):
        return handlers.get_bucket()

    def _upload_to_minio(self, s3, bucket, key, filepath):
        handlers.upload_minio(s3=s3, filepath=filepath, bucket=bucket, key=key)
        return key

    def _flush_bucket(self, s3, bucket, prefix="documents/"):
        try:
            deleted = handlers.try_flush_bucket(s3=s3, bucket=bucket, prefix=prefix)
            self.stdout.write(f"    deleted {deleted} objects: s3://{bucket}/{prefix}")

        except ClientError as err:
            self.stderr.write(
                self.style.WARNING(
                    f"    failed to flush bucket 's3://{bucket}/{prefix}': {err}"
                )
            )

    def _flush(self):
        for model in self.FLUSH_MODELS:
            count, _ = model.objects.all().delete()
            self.stdout.write(f"deleted: {count} rows - {model.__name__}")

        user_count, _ = User.objects.all().delete()
        self.stdout.write(f"deleted: {user_count} users")

        group_count, _ = Group.objects.all().delete()
        self.stdout.write(f"deleted: {group_count} groups")

        try:
            s3 = self._get_s3_client()
            bucket = self._get_bucket()
            self._flush_bucket(s3, bucket, prefix="documents/")
        except Exception as err:
            self.stderr.write(
                self.style.WARNING(
                    f"      failed to connect to minio during flush: {err}\n"
                )
            )

        fixture_docs = Path(settings.BASE_DIR) / "fixtures" / "media" / "documents"
        if fixture_docs.exists():
            pdf_count = 0
            for pdf in fixture_docs.glob("*pdf"):
                pdf.unlink()
                pdf_count += 1

            if pdf_count:
                self._log(
                    f"    delete {pdf_count} PDFs from local path: {fixture_docs}"
                )

        self.stdout.write(self.style.WARNING("flushed app data\n"))

    def _create_groups(self):
        from django.db.models import Q

        group_perms = {
            "Viewers": ["view_"],
            "Editors": ["view_", "add_", "change_"],
            "Managers": ["view_", "add_", "change_", "delete_"],
        }
        groups = {}
        for group_name, prefixes in group_perms.items():
            try:
                group, perm_ids, created = handlers.create_group(
                    Q, group_name, prefixes, self.APP_LABEL
                )
                groups[group_name] = group
                self.stdout.write(
                    f"    {group_name}: {len(perm_ids)} permissions"
                    f" ({'created' if created else 'exists'})"
                )

            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"    FAILED on {group_name}: {exc}")
                )
        self._log(f"created: {len(groups)} groups")
        return groups

    def _create_organisations(self):
        orgs = []

        for _ in range(NUM_ORGANISATIONS):
            org = handlers.create_org(uuid, fake, random, ORG_MODES)
            orgs.append(org)

        self._log(f"created: {len(orgs)} organisations")

        return orgs

    def _create_users(self, orgs, groups):
        users = []
        su, _ = User.objects.get_or_create(
            username="admin",
            defaults=dict(
                email="admin@example.com",
                first_name="Admin",
                last_name="User",
                is_superuser=True,
                is_staff=True,
            ),
        )
        if _:
            su.set_password("admin123")
            su.save()
        users.append(su)
        self._log("created: admin / admin123")

        for org in orgs:
            for i in range(NUM_USERS_PER_ORG):
                users.append(
                    handlers.create_single_user(
                        fake, random, groups=groups, org=org, index=i
                    )
                )

        self._log(f"created: {len(users)} users + profiles")
        return users

    def _create_processes(self, orgs):
        processes = []
        for org in orgs:
            for _ in range(NUM_PROCESSES_PER_ORG):
                p = handlers.create_process(
                    uuid, fake, random, org, PROCESS_MODES, COMMODITIES
                )
                processes.append(p)
        self._log(f"created: {len(processes)} processes")
        return processes

    def _create_drillholes(self, processes):
        holes = []
        for proc in processes:
            for i in range(NUM_DRILLHOLES_PER_PROCESS):
                h = handlers.create_drillhole(uuid, random, proc, index=i)
                holes.append(h)

        self._log(f"created: {len(holes)} drillholes")
        return holes

    def _create_prospects(self, processes):
        prospects = []
        for proc in processes:
            for _ in range(NUM_PROSPECTS_PER_PROCESS):
                pr = handlers.create_prospect(uuid, fake, random, proc)
                prospects.append(pr)
        self._log(f"created: {len(prospects)} prospects")
        return prospects

    def _create_tenements(self, processes):
        tenements = []
        for proc in processes:
            for j in range(NUM_TENEMENTS_PER_PROCESS):
                t = handlers.create_tenement(uuid, random, proc)
                tenements.append(t)
        self._log(f"created: {len(tenements)} tenements")
        return tenements

    def _create_documents(self, processes, users):
        fixture_docs_dir = self.fixtures_media_dir
        fixture_docs_dir.mkdir(parents=True, exist_ok=True)

        s3 = handlers.get_s3_client()
        bucket = handlers.get_bucket()

        uploaded = 0
        docs = []

        for proc in processes:
            org_users = handlers.create_org_users(users, proc)

            for _ in range(NUM_DOCUMENTS_PER_PROCESS):
                doc = handlers.create_doc_for_process(
                    uuid=uuid,
                    random=random,
                    fake=fake,
                    s3=s3,
                    bucket=bucket,
                    fixture_docs_dir=fixture_docs_dir,
                    proc=proc,
                    org_users=org_users,
                )

                docs.append(doc)
                uploaded += 1

        self._log(f"created: {len(docs)} documents")
        self._log(f"    uploaded {uploaded} PDFs to s3://{bucket}/documents/")
        self._log(f"    fixture copies written to {fixture_docs_dir}")

        return docs

    def _create_approval_workflows(self, docs, users):
        ct = ContentType.objects.get_for_model(Document)
        managers = [u for u in users if u.is_staff]
        workflows = []
        for doc in random.sample(docs, k=min(NUM_APPROVAL_WORKFLOWS, len(docs))):
            submitted = timezone.now() - timedelta(days=random.randint(1, 60))
            status = random.choice(WORKFLOW_STATUSES)
            wf = ApprovalWorkflow.objects.create(
                object_id=doc.id,
                content_type=ct,
                workflow_type=random.choice(WORKFLOW_TYPES),
                status=status,
                submission_notes=fake.paragraph(nb_sentences=2),
                approval_notes=fake.paragraph(nb_sentences=1)
                if status != "PENDING"
                else "",
                submitted_at=submitted,
                submitted_by=random.choice(users),
                reviewed_at=submitted + timedelta(days=random.randint(1, 14))
                if status != "PENDING"
                else None,
                approved_by=random.choice(managers) if status != "PENDING" else None,
            )
            workflows.append(wf)
        self._log(f"created: {len(workflows)} approval workflows")

    def _create_audit_logs(self, docs, users):
        ct = ContentType.objects.get_for_model(Document)
        for _ in range(NUM_AUDIT_LOGS):
            doc = random.choice(docs)
            AuditLog.objects.create(
                action=random.choice(AUDIT_ACTIONS),
                object_id=doc.id,
                content_type=ct,
                user=random.choice(users),
                description=fake.sentence(),
                ip_address=fake.ipv4_private(),
                user_agent=fake.user_agent(),
                timestamp=timezone.now() - timedelta(days=random.randint(0, 90)),
            )

        self._log("created: audit log entries")

    def _create_document_views(self, docs, users):
        for _ in range(NUM_DOCUMENT_VIEWS):
            DocumentView.objects.create(
                document=random.choice(docs),
                user=random.choice(users),
                viewed_at=timezone.now() - timedelta(days=random.randint(0, 30)),
                ip_address=fake.ipv4_private(),
            )
        self._log("created: document views")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("starting database seeder...\n"))

        self._log("using options:")
        self._log(options)

        seed = 12345
        self._log(f"rng seed: {seed}")

        random.seed(seed)
        Faker.seed(seed)
        fake.unique.clear()

        self.fixtures_dir = Path(settings.BASE_DIR) / "fixtures"
        self.fixtures_media_dir = self.fixtures_dir / "media" / "documents"
        self.fixtures_media_dir.mkdir(parents=True, exist_ok=True)

        if options["flush"]:
            self._flush()
            return

        groups = self._create_groups()
        orgs = self._create_organisations()
        users = self._create_users(orgs, groups)
        processes = self._create_processes(orgs)
        drillholes = self._create_drillholes(processes)
        prospects = self._create_prospects(processes)
        tenements = self._create_tenements(processes)

        if options["gen_pdf"]:
            docs = self._create_documents(processes, users)

            self._create_approval_workflows(docs, users)
            self._create_audit_logs(docs, users)
            self._create_document_views(docs, users)

        else:
            docs = []

        total = sum(
            [
                len(orgs),
                len(users),
                len(processes),
                len(drillholes),
                len(prospects),
                len(tenements),
                len(docs),
                NUM_APPROVAL_WORKFLOWS,
                NUM_AUDIT_LOGS,
                NUM_DOCUMENT_VIEWS,
            ]
        )
        self.stdout.write(self.style.SUCCESS(f"complete: {total} objects created\n"))
