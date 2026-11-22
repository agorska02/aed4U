# Standalone AED demo server (frontend + API) — build from the hackathon/ directory:
#
#   docker build -f standalone/Dockerfile -t aed-demo .
#   docker run --rm -p 127.0.0.1:8090:8090 aed-demo                      # SQLite inside the container
#   docker compose -f standalone/docker-compose.yml up --build            # with PostgreSQL
#
# The server uses the standard library only; psycopg2 is needed for PostgreSQL (AED_DATABASE_URL).
# NOT for production: demo accounts, no HTTPS.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AED_DATABASE_URL=/data/aed_demo.sqlite3

RUN pip install --no-cache-dir psycopg2-binary==2.9.10 \
    && useradd --create-home --uid 10001 aed \
    && mkdir /data && chown aed /data

WORKDIR /app
# Same layout as the repository: server.py finds frontend/ and schema/ next to standalone/.
COPY backend/aed/__init__.py backend/aed/validation.py backend/aed/importing.py backend/aed/
COPY schema/ schema/
COPY frontend/ frontend/
COPY standalone/server.py standalone/seed.py standalone/db.py standalone/schema.sql standalone/schema.postgres.sql standalone/

USER aed
VOLUME ["/data"]
EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/api/aed-devices', timeout=2)"
CMD ["python", "standalone/server.py", "--host", "0.0.0.0", "--port", "8090"]
