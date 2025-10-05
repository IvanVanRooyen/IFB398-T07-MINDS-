# Orefox KMS 

## some quick notes on how this branch currently works

apologies if it is a little unclear - this explanation was very quickly thrown together at 5.50am.
 
i have not had time to exported the dependencies to a `requirements.txt` yet, but python packages should be in `src/pyproject.toml` under `[dependencies]`; i find life is significantly streamlined by using `uv` to manage and run everything:

- package + environment management with [`uv`](https://docs.astral.sh/uv/getting-started/installation/) - after installation:
  ```
  # install python 3.13 + dependencies into `src/.venv`:
  cd src
  uv sync
  
  uv run ./manage.py runserver
  ```
  
- instead of calling `python [command]` directly, run through `uv run [command]`, e.g `uv run ./manage.py runserver`.

i am using [`bun`](https://bun.com/) for node package management - after installing `bun` (or whatever tool - `npm`, `deno`, `pnpm`, `yarn`, ...):

```
# install node dependencies 
bun install

# run vite's development server
bun run dev
```
  
for the time being, development requires two terminal windows - one for the django backend, the other for the node frontend:
```
bun run dev # frontend

# ...

uv run ./manage.py runserver # frontend
```

`bun run build` bundles the frontend for production and `uv run ./manage.py collectstatic` pulls the bundled js + css into `src/staticfiles`.
django will use this when `DJANGO_DEBUG` is set to `False` in either `.env` or in `config/settings.py`.  

> original readme content below 

---

This proof-of-concept demonstrates how documents (e.g., PDFs of exploration reports) and geospatial datasets (projects, tenements) can be centrally stored, tagged, and accessed via a web interface with geospatial intelligence.

---

## Features

- **Django + GeoDjango + HTMX**
  - Web application with interactive templates.
  - GeoDjango adds spatial fields and admin map widgets.
  - HTMX makes forms/pages reactive without a full SPA.

- **PostgreSQL + PostGIS**
  - Relational DB with geospatial support.
  - Store and query projects, tenements, drillholes with spatial operators.

- **MinIO**
  - S3-compatible object storage.
  - Stores PDFs and other file uploads outside the database.

- **Docker Compose**
  - One command to start the entire stack.
  - Encapsulates dependencies and ensures consistency across machines.

---

## 🛠 Technology Choices

- **Django**: mature, batteries-included framework with ORM, migrations, authentication, and admin out of the box.  
- **GeoDjango**: geospatial extensions to handle exploration/mining geometries (POINT, POLYGON, MULTIPOLYGON).  
- **HTMX**: lightweight library for interactivity (upload forms, dynamic tables) without heavy frontend frameworks.  
- **PostgreSQL + PostGIS**: best-in-class geospatial database, perfect for “find all documents within 5km of this tenement” queries.  
- **MinIO**: local/cloud-ready, S3-compatible storage for large binary files like PDFs.  
- **Docker**: consistent developer and deployment environment. No “it works on my machine” issues.  
- **Docker Compose**: orchestrates DB, storage, and app together.

---

## 📂 Repository Structure

### IFB398-T07-MINDS/

├── .env.example              # Example environment variables (copy to .env)

├── docker-compose.yml        # Defines services: db, minio, create-bucket, web
https://docs.npmjs.com/downloading-and-installing-node-js-and-npm
├── infra/

│   └── web/

│       ├── Dockerfile        # Builds the Django web container

│       └── requirements.txt  # Python dependencies

├── manage.py                 # Django entrypoint

├── config/                   # Django project config

│   ├── settings.py           # Django + PostGIS + MinIO configuration

│   ├── urls.py               # URL routes (admin, core app, healthcheck)

│   └── ...

├── core/                     # First Django app

│   ├── models.py             # ProjectOp + Document models

│   ├── admin.py              # Registers models with admin (GIS map widget)

│   ├── views.py              # Home + upload views

│   ├── urls.py               # Core routes

│   └── ...

└── templates/

├── base.html             # Shared HTML layout

├── core/home.html        # Homepage: lists projects & documents

└── core/upload.html      # Document upload form

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/IvanVanRooyen/IFB398-T07-MINDS-.git
cd IFB398-T07-MINDS
```

### 2. Create a .env file or copy from .env.example

```bash
POSTGRES_DB=orefox
POSTGRES_USER=orefox
POSTGRES_PASSWORD=orefoxpw
POSTGRES_HOST=db
POSTGRES_PORT=5432

DJANGO_SECRET_KEY=dev-please-change
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET=documents
MINIO_ENDPOINT=http://minio:9000
```

### 3. Build and start the stack

```bash
docker compose build web
docker compose up -d db minio create-bucket
```

### 4. Run migrations & create an admin user

```bash
docker compose run --rm web bash -lc "python manage.py makemigrations && python manage.py migrate"
docker compose run --rm web bash -lc "python manage.py createsuperuser"
```

Follow the prompts for username/email/password.

### 5. Start the web app

```bash
docker compose up -d web
```

### Access the Services

- App Home → <http://localhost:8000>
- Django Admin → <http://localhost:8000/admin>
- MinIO Console → <http://localhost:9001> (login with MINIO_ROOT_USER/MINIO_ROOT_PASSWORD from .env)

## How It Works:

**ProjectOp model**

- Represents a mining/ exploration project or operation, with a geometry (polygon).

**Document model**

- Stores metadata (title, year, doc type) and uploads files to MinIO.
- Linked to a project for context.

**Admin interface**

- Lets you draw polygons on a map (via GeoDjango) and manage data.

**Upload page**

- Basic UI to upload PDFs and tag them with metadata.

## Development Notes

Rebuild the web image after changing infra/web/Dockerfile or requirements.txt:

```bash
docker compose build --no-cache web
```
](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm)
**Apply model changes:**

```bash
docker compose run --rm web bash -lc "python manage.py makemigrations && python manage.py migrate"
```

**Logs:**

```bash
docker compose logs -f web
docker compose logs -f db
```

**DB Shell:**

```bash
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB
```
