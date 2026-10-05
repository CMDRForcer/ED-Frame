FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY server/catalog_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ed_companion /app/ed_companion
COPY ed_data /app/ed_data
COPY server/catalog_service/edframe_catalog /app/edframe_catalog

RUN python -m compileall -q /app/ed_companion /app/edframe_catalog

RUN useradd --create-home --uid 10001 catalog
USER catalog

CMD ["uvicorn", "edframe_catalog.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
