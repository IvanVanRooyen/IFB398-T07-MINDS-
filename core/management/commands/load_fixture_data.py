"""
Handles MinIO population from fixture data in addition to loading fixture data
"""

from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand

from .seeding import handlers


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--filename",
            type=str,
            default=None,
            help="name of fixture file to load (default: `generated_with_docs.json`)",
        )

        parser.add_argument(
            "--directory",
            type=str,
            default=None,
            help="path to fixture directory (default: `BASE_DIR/fixtures`)",
        )

    def _get_s3_client(self):
        return handlers.get_s3_client()

    def _get_bucket(self):
        return handlers.get_bucket()

    def handle(self, *args, **options):
        fixture_json = options["filename"] or "generated_with_docs.json"
        fixture_dir = Path(
            options["directory"] or (Path(settings.BASE_DIR) / "fixtures")
        )

        fixture_filepath = fixture_dir / fixture_json
        fixture_media = fixture_dir / "media"

        if not fixture_media.exists():
            self.stdout.write(
                self.style.ERROR(f"   no directory found at '{fixture_dir}'")
            )

            exit(1)

        try:
            s3 = handlers.get_s3_client()
            bucket = handlers.get_bucket()

            try:
                s3.head_bucket(Bucket=bucket)

            except ClientError:
                self.stdout.write(f"    unable to get bucket '{bucket}' - creating")
                s3.create_bucket(Bucket=bucket)

        except Exception as err:
            self.stderr.write(self.style.ERROR(f"cannot connect to MinIO: {err}"))
            return

        uploaded = 0
        skipped = 0

        for src_file in fixture_media.rglob("*"):
            if not src_file.is_file():
                continue

            object_key = str(src_file.relative_to(fixture_media))

            try:
                res = s3.head_object(Bucket=bucket, Key=object_key)
                if res["ContentLength"] == src_file.stat().st_size:
                    self.stdout.write(
                        self.style.WARNING(
                            f"skipping upload for file '{object_key}': exists"
                        )
                    )

                    skipped += 1
                    continue

            except ClientError:
                # this is an expected exception when the file does not exist
                pass

            handlers.upload_minio(
                s3=s3, filepath=src_file, bucket=bucket, key=object_key
            )
            uploaded += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  s3://{bucket}/ -> uploaded: {uploaded}; skipped: {skipped}"
            )
        )
