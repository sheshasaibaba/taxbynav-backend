# TaxByNav Backend - run with uvicorn, suitable for Google Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Install production dependencies (no dev); app package required for setuptools
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Migrations and Alembic config
COPY migrations ./migrations
COPY alembic.ini ./

# Cloud Run sets PORT at runtime (default 8080)
ENV PORT=8080
EXPOSE 8080

# Run migrations then start the server (no --reload in production)
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
