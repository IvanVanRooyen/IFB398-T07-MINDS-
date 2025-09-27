FROM python:3.11-slim

RUN apt-get update && apt-get install -y     binutils libproj-dev gdal-bin postgresql-client     build-essential libpq-dev curl     && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
