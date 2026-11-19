# Development and CI

## Supported local environment

The supported local profile is `compose.dev.yml`: Django, a separate report worker, PostgreSQL/PostGIS, Redis and a private filesystem-backed document volume. Only the web app is published, at `http://localhost:8000`, bound to loopback. Database, cache and document storage have no host ports. No model, object-store account or telemetry service is needed for manual report workflows.

Use Docker Engine/Desktop with Compose v2.24 or newer. Linux/amd64 is the verified platform; other architectures need compatible PostGIS images or suitable emulation. The Python image, PostGIS and Redis images are pinned by digest. The Python version is recorded in `.python-version`.

```bash
cp .env.example .env
```

Replace the secret/password placeholders. `DEMO_PASSWORD` must contain at least twelve characters. The minimal profile derives its database connection from `POSTGRES_*`, avoiding independent web/database credentials. Required variables fail validation before startup:

```bash
docker compose -f compose.dev.yml config --quiet
docker compose -f compose.dev.yml up --build -d
```

A one-shot `migrate` service waits for the healthy database. Web and worker wait for successful migration, and Redis health. Application source is copied into the image; a source checkout or host virtual environment is not mounted. After source changes, rebuild with the same `up --build` command.

The image uses locked Python dependencies and GDAL system libraries. It does not require a prebuilt local image or install libraries from a developer's machine.

## Synthetic scenario

```bash
docker compose -f compose.dev.yml exec web python manage.py seed_demo
```

Log in as `demo-geologist` or `demo-reviewer` using the `DEMO_PASSWORD` value used when creating the accounts. Both are ordinary application users, not platform administrators. The reviewer has the relevant review permissions.

The scenario contains a bounded project/permit/prospect, three drillholes, survey/lithology/assay records, a real synthetic DOCX, linked evidence and a manually prepared report with tables and a collar figure. One collar intentionally has no coordinates; negative Au values preserve the source below-detection notation. All data is explicitly synthetic.

Repeat seeding preserves existing values, files and passwords. To replace the synthetic project and its records:

```bash
docker compose -f compose.dev.yml exec web python manage.py seed_demo --reset
```

Reset is restricted to the fixed synthetic project identity; it retains accounts, the organisation and other projects. Any additional records created inside that synthetic project are part of the reset scope. File cleanup follows a successful database commit; failed seed/reset operations retain the previous dataset. The command refuses to run outside the enabled local profile, with non-filesystem storage or without the explicit password.

For platform administration, create a separate superuser rather than promoting the demo accounts:

```bash
docker compose -f compose.dev.yml exec web python manage.py createsuperuser
```

## Automated checks

```bash
docker compose -f compose.dev.yml --profile test run --rm checks
docker compose -f compose.dev.yml --profile test run --rm checks sh scripts/audit.sh
```

`checks` runs `scripts/check.sh`: lock consistency, generated requirements drift, whole-repository Ruff, Django system checks, migrations, schema drift, the full PostGIS suite and offline AI regression evaluation. The runtime dependency audit is a separate advisory-service network check; it exits unsuccessfully on known findings or an unavailable audit service.

Tests use the checked-in `config.test_settings`, real PostGIS and Redis database 1, temporary filesystem storage and a fast test-only password hasher. They never read `.env`, require MinIO or use a configured real model. Model error-path calls are directed to an unreachable loopback endpoint with a one-second timeout. The application cache uses Redis database 0.

`config.test_settings` still accepts database connection variables; use the disposable Compose services, not production credentials. Historical migration 0011 creates a database reader role, so the disposable database account needs extension/role and test-database creation privileges. These development credentials are not a least-privilege production setup.

## HTTP and worker smoke check

With the web app and worker running:

```bash
docker compose -f compose.dev.yml exec -T web python -m scripts.smoke
```

This repeats the seed, checks authenticated routes and private source bytes over real HTTP, submits a manual report request and waits for the separate worker to publish it. It creates a synthetic verification draft on each run. No model response is mocked or required for this manual path.

## Dependencies

`pyproject.toml` is the application/development dependency definition. `uv.lock` contains exact resolutions and artifact hashes. The Docker build uses uv 0.11.6 and a frozen lock. Runtime dependencies and development tools are installed into `/opt/venv`, outside the source tree.

`infra/web/requirements.txt` is a generated, hash-pinned runtime export for pip compatibility; do not maintain it independently. With the recorded Python and uv available, update dependencies deliberately:

```bash
uv lock --upgrade
uv export --locked --no-dev --no-emit-project --no-header --output-file infra/web/requirements.txt
```

Rebuild and run checks/audit after dependency changes. Review base-image digests separately; apt packages are installed from the pinned distribution's repositories, so the image build is not claimed to be byte-for-byte reproducible across time. For native execution, install the same GIS libraries and run `uv sync --frozen`; configure development PostGIS/Redis connection variables explicitly. Docker is the supported clean-start path.

## CI

`.github/workflows/ci.yml` runs on pushes and pull requests with read-only repository permissions. It builds the same development target, runs the same check and audit scripts, starts the development app/worker and runs the HTTP smoke check. It uses disposable credentials/volumes and cleans them even after a failure. Checkout is pinned and does not persist Git credentials.

The commands are verified locally; the hosted workflow will execute when these changes are pushed. A local pass is not presented as a completed GitHub run.

## Optional services and cleanup

AI-assisted drafting can use an installed provider/model via the example environment; model weights are never downloaded automatically. The separate legacy `docker-compose.yml` retains S3/MinIO and telemetry configuration. Its application build now uses the repository context/lock, but the whole legacy stack is outside the supported minimal-profile verification. It includes published infrastructure ports and anonymous-administrator Grafana settings; it is not a public deployment definition.

Stop the supported stack while keeping local data:

```bash
docker compose -f compose.dev.yml down
```

Deleting its named volumes also removes that profile's database and document data. Only do so when intentionally discarding a disposable environment. Production TLS/static serving, least-privilege credentials, backups, retention/admission limits, broad accessibility and release/demo policy remain separate work.
