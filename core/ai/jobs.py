"""Durable generation jobs; PostgreSQL owns claims, cancellation and publication."""

import logging
import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.access import (
    CLEARANCE_LEVELS,
    clearance_level,
    document_filter,
    require_author,
    require_record_access,
)
from core.models import AuditLog, log_audit
from core.models import ReportGenerationJob as Job
from core.models import ReportGenerationSubmission as Submission

from .composition import (
    FLAGS,
    MAX_DOCUMENTS,
    ReportCompositionForm,
    _fingerprint,
    _hash,
    _json,
    compose_report,
    composition_context,
    eligible_documents,
    persist_composition,
)

log = logging.getLogger(__name__)
ACTIVE = (Job.Status.QUEUED, Job.Status.RUNNING)
STAGES = {
    "QUEUED": "Waiting for an available worker",
    "VALIDATING": "Checking the request",
    "READING_EVIDENCE": "Reading selected evidence",
    "GENERATING_DRAFT": "Generating the draft",
    "SAVING_DRAFT": "Saving the draft",
    "COMPLETED": "Draft saved",
    "FAILED": "Generation failed",
    "CANCELLED": "Generation cancelled",
}


class JobStopped(Exception):
    pass


def visible_jobs(user):
    qs = Job.objects.filter(requested_by=user)
    if not user.is_superuser:
        org_id = getattr(getattr(user, "profile", None), "organisation_id", None)
        rank = CLEARANCE_LEVELS.get(clearance_level(user), -1)
        allowed = [key for key, value in CLEARANCE_LEVELS.items() if value <= rank]
        qs = (
            qs.filter(
                organisation_id=org_id, process__organisation_id=org_id, clearance_level__in=allowed
            )
            if org_id
            else qs.none()
        )
    return qs


def _lease():
    return timedelta(
        seconds=max(
            getattr(settings, "REPORT_JOB_LEASE_SECONDS", 600),
            int(os.getenv("GRANITE_TIMEOUT", "120")) + 60,
        )
    )


def expire_jobs(qs=None):
    return (
        (qs if qs is not None else Job.objects.all())
        .filter(status=Job.Status.RUNNING, lease_expires_at__lte=timezone.now())
        .update(
            status=Job.Status.FAILED,
            stage="FAILED",
            error_code="WORKER_INTERRUPTED",
            error_message="The worker stopped responding. You can retry this generation.",
            retryable=True,
            run_token=None,
            lease_expires_at=None,
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
    )


def _form_payload(form):
    data = form.cleaned_data
    return {
        "composer_version": "1",
        "process_id": str(data["process_id"].pk),
        "report_title": data["report_title"],
        "document_ids": [str(doc.pk) for doc in data["document_ids"]],
        **{
            key: data[key] for key in ("drafting_mode", "report_type", "tone", "instructions", "source_mode", *FLAGS)
        },
    }


def enqueue(form, request_id=None):
    user = form.user
    require_author(user)
    if not user.is_active:
        raise PermissionDenied
    if not form.is_bound:
        raise ValidationError("Report options are invalid.")
    try:
        key = uuid.UUID(str(request_id)) if request_id else uuid.uuid4()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Invalid submission key. Review and submit the form again.") from exc
    # Receipts identify the submitted options, independently of later source edits.
    intent = {name: form[name].value() for name in form.fields}
    intent["document_ids"] = sorted(str(value) for value in (intent["document_ids"] or []))
    intent_hash = _hash(_json(intent))
    with transaction.atomic():
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        previous = (
            Submission.objects.select_related("job")
            .filter(requested_by=user, request_id=key)
            .first()
        )
        if previous:
            if not visible_jobs(user).filter(pk=previous.job_id).exists():
                raise PermissionDenied
            if previous.request_hash != intent_hash:
                raise ValidationError(
                    "This form already started a different generation. Review your options and submit again."
                )
            return previous.job
        if not form.is_valid():
            raise ValidationError("Report options are invalid.")
        process, prospect = form.cleaned_data["process_id"], form.prospect
        require_record_access(user, process)
        if prospect:
            require_record_access(user, prospect)
        eligible = eligible_documents(user, process, prospect)
        if form.cleaned_data["source_mode"] == "selected":
            ids = [doc.pk for doc in form.cleaned_data["document_ids"]]
            docs = list(eligible.filter(pk__in=ids).order_by("pk"))
            if len(docs) != len(ids):
                raise ValidationError("Source access changed. Review your selection.")
        else:
            docs = list(eligible[:MAX_DOCUMENTS])
        payload = {
            "form": _form_payload(form),
            "source_ids": [str(doc.pk) for doc in docs],
            "fingerprints": {str(doc.pk): _fingerprint(doc) for doc in docs},
            "context_fingerprint": _hash(_json(composition_context(process, prospect))),
        }
        digest = _hash(
            _json(
                {
                    "payload": payload,
                    "process": str(process.pk),
                    "organisation": str(process.organisation_id),
                    "prospect": str(prospect.pk) if prospect else None,
                    "clearance": clearance_level(user),
                }
            )
        )
        expire_jobs(visible_jobs(user))
        job = Job.objects.filter(requested_by=user, request_hash=digest, status__in=ACTIVE).first()
        if job is None:
            job = Job.objects.create(
                requested_by=user,
                organisation=process.organisation,
                process=process,
                prospect=prospect,
                clearance_level=clearance_level(user),
                payload=payload,
                request_hash=digest,
                title=form.cleaned_data["report_title"]
                or (
                    f"{prospect.name} — Prospect Report"
                    if prospect
                    else f"{process.name or 'Project'} Report"
                ),
            )
            log_audit(user, AuditLog.ActionType.CREATE, job, "Queued report generation")
        Submission.objects.create(
            requested_by=user, request_id=key, request_hash=intent_hash, job=job
        )
        return job


def claim_next():
    expire_jobs()
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status=Job.Status.QUEUED)
            .order_by("created_at", "pk")
            .first()
        )
        if job is None:
            return None
        job.status = Job.Status.RUNNING
        job.stage = "VALIDATING"
        job.run_token = uuid.uuid4()
        job.attempts += 1
        job.started_at = timezone.now()
        job.finished_at = None
        job.lease_expires_at = timezone.now() + _lease()
        job.error_code = ""
        job.error_message = ""
        job.retryable = False
        job.save()
        return job.pk, job.run_token


def _request(job):
    user = get_user_model().objects.select_related("profile").get(pk=job.requested_by_id)
    require_author(user)
    if not user.is_active:
        raise PermissionDenied
    require_record_access(user, job.process)
    if job.organisation_id != job.process.organisation_id:
        raise PermissionDenied
    if CLEARANCE_LEVELS.get(clearance_level(user), -1) < CLEARANCE_LEVELS.get(
        job.clearance_level, 99
    ):
        raise PermissionDenied
    if job.prospect:
        require_record_access(user, job.prospect)
        if (
            job.prospect.process_id != job.process_id
            or job.prospect.organisation_id != job.organisation_id
        ):
            raise PermissionDenied
    form = ReportCompositionForm(job.payload["form"], user=user, prospect=job.prospect)
    if not form.is_valid():
        raise ValidationError(
            "The request or source access changed. Review the selection before generating again."
        )
    return user, form


def _snapshot_valid(job, user):
    docs = list(
        eligible_documents(user, job.process, job.prospect).filter(pk__in=job.payload["source_ids"])
    )
    expected = job.payload["fingerprints"]
    if len(docs) != len(expected) or any(
        expected.get(str(doc.pk)) != _fingerprint(doc) for doc in docs
    ):
        raise ValidationError(
            "Source files changed. Review the selection and start a new generation."
        )
    if (
        _hash(_json(composition_context(job.process, job.prospect)))
        != job.payload["context_fingerprint"]
    ):
        raise ValidationError(
            "Project or prospect inputs changed. Review them before generating again."
        )


def _advance(job_id, token, stage):
    changed = Job.objects.filter(
        pk=job_id, status=Job.Status.RUNNING, run_token=token, lease_expires_at__gt=timezone.now()
    ).update(stage=stage, lease_expires_at=timezone.now() + _lease(), updated_at=timezone.now())
    if not changed:
        expire_jobs(Job.objects.filter(pk=job_id))
        raise JobStopped
    if stage == "GENERATING_DRAFT":
        current = Job.objects.select_related("process", "prospect").get(pk=job_id)
        user, _ = _request(current)
        _snapshot_valid(current, user)


def _fail(job_id, token, code, message, retryable):
    Job.objects.filter(pk=job_id, status=Job.Status.RUNNING, run_token=token).update(
        status=Job.Status.FAILED,
        stage="FAILED",
        error_code=code,
        error_message=message,
        retryable=retryable,
        run_token=None,
        lease_expires_at=None,
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )


def execute(job_id, token):
    try:
        job = Job.objects.select_related("process", "prospect").get(pk=job_id)
        _advance(job_id, token, "VALIDATING")
        user, form = _request(job)
        bundle = compose_report(
            form,
            document_ids=job.payload["source_ids"],
            expected_fingerprints=job.payload["fingerprints"],
            expected_context=job.payload["context_fingerprint"],
            checkpoint=lambda stage: _advance(job_id, token, stage),
        )
        with transaction.atomic():
            current = (
                Job.objects.select_for_update(of=("self",))
                .select_related("process", "prospect")
                .get(pk=job_id)
            )
            if (
                current.status != Job.Status.RUNNING
                or current.run_token != token
                or current.lease_expires_at <= timezone.now()
            ):
                raise JobStopped
            # Re-read the actor and inputs after the external call, before publication.
            user, _ = _request(current)
            _snapshot_valid(current, user)
            report = persist_composition(
                user, current.process, bundle, current.title, current.prospect
            )
            current.result = report
            current.status = Job.Status.SUCCEEDED
            current.stage = "COMPLETED"
            current.run_token = None
            current.lease_expires_at = None
            current.finished_at = timezone.now()
            current.save()
    except (JobStopped, Job.DoesNotExist):
        expire_jobs(Job.objects.filter(pk=job_id))
    except PermissionDenied:
        _fail(job_id, token, "ACCESS_CHANGED", "Your access changed. No draft was saved.", False)
    except ValidationError as exc:
        empty = getattr(exc, "code", None) == "empty_generation"
        _fail(
            job_id,
            token,
            "GENERATION_FAILED" if empty else "INPUT_CHANGED",
            " ".join(exc.messages),
            empty,
        )
    except Exception:
        log.exception("Report generation job %s failed", job_id)
        _fail(
            job_id,
            token,
            "GENERATION_FAILED",
            "Generation failed. You can retry this request.",
            True,
        )


def run_next():
    claimed = claim_next()
    if claimed:
        execute(*claimed)
    return claimed


def cancel(user, job_id):
    require_author(user)
    if not user.is_active:
        raise PermissionDenied
    with transaction.atomic():
        job = visible_jobs(user).select_for_update().get(pk=job_id)
        if job.status in ACTIVE:
            job.status = Job.Status.CANCELLED
            job.stage = "CANCELLED"
            job.run_token = None
            job.lease_expires_at = None
            job.finished_at = timezone.now()
            job.retryable = True
            job.save()
            log_audit(user, AuditLog.ActionType.EDIT, job, "Cancelled report generation")
        return job


def retry(user, job_id):
    require_author(user)
    if not user.is_active:
        raise PermissionDenied
    with transaction.atomic():
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        job = (
            visible_jobs(user)
            .select_for_update(of=("self",))
            .select_related("process", "prospect")
            .get(pk=job_id)
        )
        expire_jobs(Job.objects.filter(pk=job_id))
        job.refresh_from_db()
        if job.status in ACTIVE:
            return job
        if job.status not in (Job.Status.FAILED, Job.Status.CANCELLED) or not job.retryable:
            raise ValidationError("Review the request in the composer before generating again.")
        try:
            _request(job)
            _snapshot_valid(job, user)
        except (ValidationError, PermissionDenied):
            job.error_code = "INPUT_CHANGED"
            job.retryable = False
            job.error_message = (
                "The inputs or access changed. Review the request before generating again."
            )
            job.save()
            return job
        other = (
            Job.objects.filter(requested_by=user, request_hash=job.request_hash, status__in=ACTIVE)
            .exclude(pk=job.pk)
            .first()
        )
        if other:
            return other
        job.status = Job.Status.QUEUED
        job.stage = "QUEUED"
        job.error_code = ""
        job.error_message = ""
        job.finished_at = None
        job.retryable = False
        job.save()
        log_audit(user, AuditLog.ActionType.EDIT, job, "Retried report generation")
        return job


def job_card(user, job):
    url = None
    if job.result_id:
        try:
            require_record_access(user, job.result)
            if not job.result.source_documents.exclude(document_filter(user)).exists():
                from django.urls import reverse

                url = reverse("saved_report_editor", args=[job.result_id])
        except PermissionDenied:
            pass
    can_write = True
    try:
        require_author(user)
        if not user.is_active:
            raise PermissionDenied
    except PermissionDenied:
        can_write = False
    return {
        "id": str(job.pk),
        "title": job.title,
        "status": job.status,
        "status_label": job.get_status_display(),
        "stage": STAGES.get(job.stage, job.stage),
        "attempts": job.attempts,
        "error": job.error_message
        or (
            "The completed draft is no longer accessible."
            if job.status == Job.Status.SUCCEEDED and not url
            else ""
        ),
        "can_cancel": can_write and job.status in ACTIVE,
        "can_retry": can_write
        and job.retryable
        and job.status in (Job.Status.FAILED, Job.Status.CANCELLED),
        "report_url": url,
        "active": job.status in ACTIVE,
    }
