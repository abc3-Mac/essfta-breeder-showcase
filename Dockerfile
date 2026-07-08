# ESSFTA Breeder Showcase — FastAPI + Playwright (Chromium for PDF assembly)
# Pin to bookworm: Playwright's --with-deps font packages (ttf-unifont,
# ttf-ubuntu-font-family) were dropped in Debian trixie, which the plain
# python:3.12-slim tag now tracks.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium + its OS libraries (needed to render the booklet PDF)
RUN playwright install --with-deps chromium

COPY app ./app

# Persistent data lives on mounted volumes
ENV SHOWCASE_DATA_DIR=/data \
    SHOWCASE_UPLOAD_DIR=/uploads
VOLUME ["/data", "/uploads"]

EXPOSE 8790
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8790"]
