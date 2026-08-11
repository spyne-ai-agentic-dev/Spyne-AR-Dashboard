# AR Collections Dashboard — Python/Streamlit service for ECS Fargate.
# Runtime config is injected by ECS as APP_SECRETS; no ENV for runtime values.

FROM python:3.11-slim

# nginx fronts Streamlit to serve the platform health-check path.
# gettext-base provides envsubst for rendering the nginx config.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx gettext-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so layer caching survives application edits.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code and assets.
COPY app.py ./
COPY collections_dashboard.py management_dashboard.py ./
COPY email_roles.json ./
COPY spyne_logo.png spyne-logo-dark.png ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY docker/ ./docker/

# Non-root runtime user; it needs to write the generated secrets file,
# the SQLite cache, and nginx's temp/pid files (all under /app or /tmp).
RUN useradd --system --uid 10001 --create-home appuser \
    && chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/.streamlit \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 3000

CMD ["/app/docker/entrypoint.sh"]
