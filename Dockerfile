# CausalImpact demo image: API (default) or dashboard (see docker-compose.yml).
# Dependencies are installed from requirements.lock, exported from uv.lock, so the image
# uses exactly the locked versions.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .

COPY scripts ./scripts
RUN python scripts/make_demo_data.py --out /app/data/demo \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/var \
    && chown -R app /app/var /app/data

USER app
ENV CAUSALIMPACT_ENV=production \
    CAUSALIMPACT_DB_URL=sqlite:////app/var/causalimpact.db \
    CAUSALIMPACT_LOG_LEVEL=INFO
EXPOSE 8000 8501

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "--factory", "causalimpact.api.server:build_app", "--host", "0.0.0.0", "--port", "8000"]
