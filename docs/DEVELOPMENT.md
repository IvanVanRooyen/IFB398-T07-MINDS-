# Development setup

## Environment

Use Python 3.11 and the dependencies in `infra/web/requirements.txt`, including the system GIS libraries installed by `infra/web/Dockerfile`. PostgreSQL/PostGIS is required for spatial fields, full-text search and transaction/concurrency tests; SQLite is not a substitute. Redis and S3-compatible storage support the normal application configuration.

Copy `.env.example` to `.env` and replace the placeholders. The application reads this file from the repository root. Compose also reads `POSTGRES_*` and storage credentials from it. The database name/user/password must match their corresponding `DB_*` values. Historical migration 0011 also requires `GF_PG_READER_USER` and `GF_PG_READER_PASS` and permission to create the reader role.

The root `pyproject.toml` and lockfile are not yet the complete application dependency definition. Use the container requirements for the current application; consolidating and locking dependency installation is a release task.

## Application services

```bash
docker compose up --build web report-worker
docker compose exec web python manage.py createsuperuser
```

This starts the selected services and their database/cache/storage dependencies. It does not select the whole telemetry stack. Web startup runs migrations. The worker tolerates the database/schema startup race; it does not run migrations itself.

The existing development web endpoint is `http://localhost:8000`. The supplied Compose definition also publishes database, Redis and storage ports. Check for conflicts and keep it on a trusted development machine. It is not a production deployment definition. The complete fresh-install storage/telemetry path remains unverified.

For an environment started outside Compose, migrate and run Django and the worker in separate processes:

```bash
python manage.py migrate
python manage.py runserver
python manage.py run_report_worker
```

The worker can process one queue iteration with `--once`, or use a positive `--poll-interval`. Manual report outlines still require the worker but do not require an available model.

## AI configuration

`GRANITE_BACKEND=ollama` uses `${OLLAMA_URL}/api/generate`. The default client model is `granite3.2:8b-instruct-fp16`; the example environment makes that choice explicit. Run an installed model supported by the selected provider, and record the configuration used for evaluation. The application does not provision model weights.

An optional `hf` adapter uses `HF_INFERENCE_URL` and `HF_TOKEN`. An adapter's presence is not evidence that its live deployment has been validated.

`GRANITE_TIMEOUT` defaults to 120 seconds. `REPORT_JOB_LEASE_SECONDS` defaults to 600; the effective lease is at least the provider timeout plus 60 seconds. Lease refresh occurs at stages, not during an inference heartbeat.

## Data and administration

Configure an organisation and user profile after creating a platform superuser. Ordinary application roles do not grant platform-admin access. Existing fixtures and `load_fixture_data` are inherited development utilities; a curated resettable demo seed is still planned. Do not present fixture loading as a complete demonstration environment.

## Tests and evaluation

```bash
python manage.py test core --noinput
python manage.py makemigrations --check --dry-run
python manage.py evaluate_ai --check --output /tmp/minds-evaluation.json
```

The test database account needs permission to create/drop its test database and the extensions/reader role required by historical migrations. Tests make database changes only in the configured test database; run them with development credentials and storage. The last verified integration environment used PostGIS/Redis, isolated filesystem storage and a fast test password hasher. A repository-owned equivalent and CI are the next milestone; the commands above do not imply that fresh-install automation is complete.

[Verification scope](VERIFICATION.md) records the checks and qualifications.

## Deployment work still required

The current stack runs Django's development server, loads some browser assets from CDNs and includes anonymous-administrator Grafana settings. Host/origin configuration, TLS, static assets, least-privilege credentials, dependency updates, storage lifecycle, backups, job admission/retention and operations checks must be addressed for a deployed release. No production configuration or public demo is claimed.
