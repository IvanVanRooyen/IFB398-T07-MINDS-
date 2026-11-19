"""Exercise the synthetic scenario over real HTTP and the separate report worker."""

import hashlib
import json
import os
import time
import uuid
from urllib.parse import parse_qs, urlparse

import django
import requests

django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402

from core.management.commands.seed_demo import WRITER, identity  # noqa: E402
from core.models import Document, Drillhole, SavedReport  # noqa: E402

if not settings.DEBUG or not settings.ALLOW_DEMO_SEED:
    raise RuntimeError("HTTP smoke checks require the disposable local development profile.")

call_command("seed_demo")
original = (Drillhole.objects.count(), Document.objects.count(), SavedReport.objects.count())
call_command("seed_demo")
assert original == (
    Drillhole.objects.count(),
    Document.objects.count(),
    SavedReport.objects.count(),
)
base = "http://127.0.0.1:8000"
session = requests.Session()
for attempt in range(30):
    try:
        login = session.get(base + "/auth/login/", timeout=3)
        if login.status_code == 200:
            break
    except requests.ConnectionError:
        pass
    time.sleep(1)
else:
    raise RuntimeError("Development web server did not become ready.")
login = session.post(
    base + "/auth/login/",
    data={
        "username": WRITER,
        "password": os.environ["DEMO_PASSWORD"],
        "csrfmiddlewaretoken": session.cookies["csrftoken"],
    },
    timeout=10,
)
assert login.status_code == 200 and "sessionid" in session.cookies
for path in [
    "/",
    f"/projects/{identity('project')}/",
    f"/prospects/{identity('prospect')}/",
    "/map/",
    f"/ai/reports/{identity('report')}/view/",
]:
    assert session.get(base + path, timeout=10).status_code == 200, path
source = Document.objects.get(pk=identity("document"))
url = base + f"/documents/{source.pk}/download/"
response = session.get(url, timeout=10)
assert response.status_code == 200
assert hashlib.sha256(response.content).hexdigest() == source.checksum_sha256
assert requests.get(url, timeout=10, allow_redirects=False).status_code == 302
submitted = session.post(
    base + "/ai/reports/generate/",
    data={
        "csrfmiddlewaretoken": session.cookies["csrftoken"],
        "request_id": str(uuid.uuid4()),
        "composer_version": "1",
        "drafting_mode": "manual",
        "process_id": str(identity("project")),
        "source_mode": "selected",
        "document_ids": str(source.pk),
        "report_type": "exploration",
        "tone": "technical",
        "report_title": "Synthetic HTTP verification draft",
        "include_references": "on",
    },
    timeout=10,
    allow_redirects=False,
)
assert submitted.status_code == 302
job_url = base + submitted.headers["Location"]
key = parse_qs(urlparse(job_url).query)["job"][0]
for attempt in range(30):
    status = session.get(job_url + "&job_status=1", timeout=10)
    status.raise_for_status()
    job = next(row for row in status.json()["jobs"] if row["id"] == key)
    if job["status"] == "SUCCEEDED":
        break
    if job["status"] in ("FAILED", "CANCELLED"):
        raise RuntimeError("Synthetic manual job did not succeed.")
    time.sleep(1)
else:
    raise RuntimeError("Separate report worker did not complete the queued request.")
assert session.get(base + job["report_url"], timeout=10).status_code == 200
report = SavedReport.objects.get(generation_job__pk=key)
assert report.generation_manifest["backend"] == "manual"
assert list(report.source_documents.values_list("pk", flat=True)) == [source.pk]
print(
    json.dumps(
        {
            "seed_repeat_safe": True,
            "authenticated_routes": 5,
            "private_document_download": True,
            "source_checksum_matches": True,
            "separate_worker_completed_manual_request": True,
            "model_required": False,
        }
    )
)
