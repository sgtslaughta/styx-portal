FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# System deps for chromium need root
RUN playwright install-deps chromium

# Non-root runtime user. Pre-create every named-volume mountpoint so a fresh
# (empty) Docker volume inherits appuser ownership on first mount — otherwise it
# is created root-owned and the non-root process cannot write to it.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data /app/data/screenshots /app/traefik-dynamic \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser app/ app/

USER appuser

# Install the browser binary into the appuser cache (no root needed)
RUN playwright install chromium

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
