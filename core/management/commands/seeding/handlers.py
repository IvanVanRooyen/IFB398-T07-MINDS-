import os

import boto3
from django.conf import settings
from django.contrib.auth.models import Group, Permission

from core.models import (
    Document,
    Drillhole,
    Organisation,
    Process,
    Prospect,
    Tenement,
    UserProfile,
)

from . import utils
from .constants import (
    CLEARANCE_LEVELS,
    CONFIDENTIALITY_LEVELS,
    DEPARTMENTS,
    DOC_TYPES,
    ROLES,
    TAG_POOL,
)
from .utils import User


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=getattr(settings, "MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=getattr(
            settings, "MINIO_ROOT_USER", os.getenv("MINIO_ROOT_USER", "minio")
        ),
        aws_secret_access_key=getattr(
            settings,
            "MINIO_ROOT_PASSWORD",
            os.getenv("MINIO_ROOT_PASSWORD", "minio12345"),
        ),
        region_name="us-east-1",  # required by boto3 but ignored by MinIO
    )


def get_bucket():
    return getattr(settings, "MINIO_BUCKET", os.getenv("MINIO_BUCKET", "documents"))


def upload_minio(s3, filepath, bucket, key):
    s3.upload_file(
        Filename=str(filepath),
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ContentType": "application/pdf"},
    )


def try_flush_bucket(s3, bucket, prefix):
    paginator = s3.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        delete_req = {"Objects": [{"Key": obj["Key"]} for obj in objects]}
        s3.delete_objects(Bucket=bucket, Delete=delete_req)
        deleted += len(objects)

    return deleted


def create_single_user(
    fake,
    random,
    groups,
    org,
    index,
):
    is_manager = index == 0
    first = fake.first_name()
    last = fake.last_name()

    suffix = fake.unique.random_int(min=100, max=9999)
    username = f"{first.lower()}.{last.lower()}.{suffix}"[:150]

    user = User.objects.create_user(
        username=username,
        email=f"{username}@{fake.free_email_domain()}",
        password="testpass123",
        first_name=first,
        last_name=last,
        is_staff=is_manager,
    )

    group_key = "Managers" if is_manager else random.choice(["Viewers", "Editors"])
    user.groups.add(groups[group_key])

    UserProfile.objects.update_or_create(
        user=user,
        defaults=dict(
            organisation=org,
            role="MANAGER" if is_manager else random.choice(ROLES),
            clearance_level=random.choice(CLEARANCE_LEVELS),
            department=random.choice(DEPARTMENTS),
            phone=fake.phone_number()[:32],
            employee_id=f"EMP-{fake.unique.random_int(min=1000, max=9999)}",
            can_approve_jorc=is_manager,
            can_approve_valmin=is_manager,
        ),
    )

    return user


def create_prospect(uuid, fake, random, proc):
    return Prospect.objects.create(
        id=uuid.uuid4(),
        name=f"{fake.last_name()} {random.choice(['Lode', 'Reef', 'Deposit', 'Zone'])}",
        organisation=proc.organisation,
        process=proc,
        geom=utils.random_point(),
    )


def create_tenement(uuid, random, proc):
    return Tenement.objects.create(
        id=uuid.uuid4(),
        name=f"ML-{random.randint(1000, 9999)}/{random.randint(1, 99):02d}",
        organisation=proc.organisation,
        process=proc,
        geom=utils.random_multipolygon(),
    )


def create_group(Q, group_name, prefixes, app_label="core"):
    group, created = Group.objects.get_or_create(name=group_name)
    q = Q()
    for prefix in prefixes:
        q |= Q(codename__startswith=prefix)
    perm_ids = list(
        Permission.objects.filter(q, content_type__app_label=app_label)
        .distinct()
        .values_list("pk", flat=True)
    )
    group.permissions.set(perm_ids)

    return group, perm_ids, created


def create_org(uuid, fake, random, org_modes):
    return Organisation.objects.create(
        id=uuid.uuid4(),
        name=fake.company()[:32],
        mode=random.choice(org_modes),
    )


def create_process(uuid, fake, random, org, mode_opts, commodity_opts):
    return Process.objects.create(
        id=uuid.uuid4(),
        name=f"{fake.city()} {random.choice(['Mine', 'Project', 'Prospect'])}",
        mode=random.choice(mode_opts),
        organisation=org,
        commodity=random.choice(commodity_opts),
        geom=utils.random_multipolygon(),
    )


def create_drillhole(uuid, random, proc, index):
    return Drillhole.objects.create(
        id=uuid.uuid4(),
        name=f"DH-{proc.name[:8].upper().replace(' ', '')}-{index + 1:03d}",
        organisation=proc.organisation,
        process=proc,
        azimuth=round(random.uniform(0, 360), 2),
        dip=round(random.uniform(-90, 0), 2),
        depth=round(random.uniform(50, 800), 2),
        collar_location=utils.random_point(),
    )


def create_org_users(users, proc):
    org_users = [
        u
        for u in users
        if hasattr(u, "userprofile")
        and getattr(u.userprofile, "organisation_id", None) == proc.organisation_id
    ]
    if not org_users:
        org_users = users[:1]

    return org_users


def create_doc_for_process(
    uuid, random, fake, s3, bucket, fixture_docs_dir, proc, org_users
):
    doc_id = uuid.uuid4()
    doc_type = random.choice(DOC_TYPES)

    filename = f"{doc_type.lower()}_{doc_id.hex[:8]}.pdf"
    object_key = f"documents/{filename}"
    fixture_path = fixture_docs_dir / filename

    checksum = utils.generate_pdf(
        doc_type=doc_type,
        org=proc.organisation,
        process=proc,
        commodity=proc.commodity,
        output_path=str(fixture_path),
    )

    upload_minio(s3=s3, filepath=fixture_path, bucket=bucket, key=str(object_key))

    d = Document.objects.create(
        id=doc_id,
        title=fake.sentence(nb_words=5)[:64],
        file=object_key,
        tags=sorted(random.sample(TAG_POOL, k=random.randint(1, 4))),
        timestamp=fake.date_between(start_date="-2y", end_date="today"),
        doc_type=doc_type,
        confidentiality=random.choice(CONFIDENTIALITY_LEVELS),
        checksum_sha256=checksum,
        created_by=random.choice(org_users),
        organisation=proc.organisation,
        process=proc,
    )

    return d
