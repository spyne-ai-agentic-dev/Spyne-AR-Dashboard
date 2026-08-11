# AR Collections Dashboard — Python/Streamlit service for ECS Fargate.
# The ALB routes the domain (spyne-ar-dashboard.spyne.ai) to this container and
# health-checks GET /health. Runtime config arrives as APP_SECRETS from Secrets
# Manager, so there is deliberately no ENV for runtime values here.

FROM python:3.11-slim

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

# Non-root runtime user. It needs to write the generated secrets file and the
# local SQLite cache, both under /app.
RUN useradd --system --uid 10001 --create-home appuser \
    && chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/.streamlit \
    && chown -R appuser:appuser /app

USER appuser

# Informational: the real port comes from APP_SECRETS.PORT at runtime.
EXPOSE 3000

CMD ["/app/docker/entrypoint.sh"]
