# Orefox KMS Sandbox (Proof of Concept)

**A Knowledge Management System (KMS) prototype for the mining & exploration industry.**

This proof-of-concept demonstrates how documents (e.g., PDFs of exploration reports) and geospatial datasets (projects, tenements) can be centrally stored, tagged, and accessed via a web interface with geospatial intelligence.

---

## Features

- **Interactive Web Dashboard (Tailwind CSS + HTMX)**
  - Clean, responsive interface styled with Tailwind CSS via CDN.
  - Sidebar navigation for all modules (Dashboard, Documents, Prospects, Drillholes, Tenements, AI Insights, Admin).
  - Upload page supports document submissions and metadata tagging.

- **Django + GeoDjango**
  - Handles ORM, migrations, authentication, and admin interface.
  - GeoDjango adds support for spatial fields (POINT, POLYGON) for exploration data

- **PostgreSQL + PostGIS**
  - Relational DB with geospatial support.
  - Store and query projects, tenements, drillholes with spatial operators.

- **MinIO**
  - S3-compatible object storage.
  - Stores PDFs and other file uploads outside the database.

- **Docker Compose**
  - Runs the database, object storage, and Django app in isolated containers.
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

├── core/dashboard.html   # Dashboard with metrics + sidebar

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
DJANGO_DEBUG=1
SECRET_KEY=your-long-random-string

POSTGRES_DB=orefox
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DB_NAME=orefox
DB_USER=postgres
DB_PASS=postgres
DB_HOST=db
DB_PORT=5432

MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio12345
MINIO_BUCKET=documents
MINIO_ENDPOINT=minio:9000
MINIO_USE_SSL=0
```

### 3. Build and start the stack

```bash
docker compose up --build
```

This launches:

- PostgreSQL + PostGIS
- MinIO (object storage + console)
- Django web app (accessible on port 8000)

### 4. Create an admin user

```bash
docker compose exec web bash -lc "python manage.py createsuperuser"
```

Follow the prompts for username/email/password.

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

## Notes

- No local Python setup required — everything runs inside Docker.
- Tailwind is loaded via Play CDN — no Node.js or build pipeline needed.
- All environment variables must come from .env (never hard-code secrets).
- Make migrations before pushing if you alter models.
- Commit templates & static files (e.g., base.html, dashboard UI) for shared frontend consistency.