FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# System deps for chromium need root
RUN playwright install-deps chromium

# Non-root runtime user
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser app/ app/

USER appuser

# Install the browser binary into the appuser cache (no root needed)
RUN playwright install chromium

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
