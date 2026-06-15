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

# Install the browser binary into the appuser cache (no root needed).
# The playwright CDN download is flaky on some CI runners (the 30s default times
# out under slow network — observed on GitLab dind). Use a generous timeout and
# retry up to 5×; still fail the build if every attempt fails.
ENV PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=180000
RUN n=0; until playwright install chromium; do \
        n=$((n+1)); [ "$n" -ge 5 ] && echo "playwright download failed after $n attempts" && exit 1; \
        echo "playwright download failed, retry $n/5 in 15s..."; sleep 15; \
    done

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
