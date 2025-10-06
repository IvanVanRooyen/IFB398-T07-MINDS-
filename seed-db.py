#!/usr/bin/env nix-shell
#! nix-shell -i python3 -p python313Packages.psycopg2-binary python313Packages.types-psycopg2 python313Packages.faker

import datetime
import random

import psycopg2
from faker import Faker

fk = Faker()

conn = psycopg2.connect("dbname=orefox user=postgres")
cur = conn.cursor()
# id | title | file | tags | timestamp | doc_type | confidentiality | checksum_sha256 | created_at | updated_at
# created_by_id | organisation_id | process_id


def make_org(cursor):
    org_name = fk.name()

    id = fk.uuid4()
    mode = "EXPLORATION"
    created_at = datetime.datetime.now()
    updated_at = datetime.datetime.now()

    cursor.execute(
        """INSERT INTO core_organisation (
            id, name, mode, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s
        )""",
        (id, org_name, mode, created_at, updated_at)
    )

    return id


def make_doc(cursor):
    id = fk.uuid4()
    title = fk.domain_word()

    tags = []

    for _ in range(10):
        tags.append(random.random() * 10)

    checksum_sha256 = fk.sha256()

    created_at = datetime.datetime.now()
    updated_at = datetime.datetime.now()

    organisation = make_org(cur)

    print(
        id,
        title,
        tags,
        checksum_sha256,
        created_at,
        updated_at,
        organisation,
    )

    cursor.execute(
        """INSERT INTO core_document (
            id, title, file, doc_type, tags,
            checksum_sha256, created_at, updated_at,
            organisation_id, confidentiality
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
        )""",
        (id,
        title,
        'file_examplefilename',
        'file_exampledoctrype',
        tags,
        checksum_sha256,
        created_at,
        updated_at,
        organisation,
        "internal",
        ),
    )


for _ in range(15):
    make_doc(cur)
    conn.commit()
