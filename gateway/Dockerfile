FROM python:3.11-slim

# System deps: nodejs for hermes browser tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Copy vendored hermes-agent source and install with all extras
COPY hermes-agent/ /opt/hermes-agent/
RUN cd /opt/hermes-agent \
    && pip install --no-cache-dir -e ".[all]"

# Web app deps (FastAPI + xterm.js bridge)
RUN pip install --no-cache-dir uvicorn fastapi python-multipart

# Create the ~/.hermes directory structure the CLI expects
RUN mkdir -p /root/.hermes/{sessions,logs,memories,skills,hooks,cron,image_cache,audio_cache}

# Copy default config files from the repo
RUN cp /opt/hermes-agent/.env.example /root/.hermes/.env \
    && cp /opt/hermes-agent/cli-config.yaml.example /root/.hermes/config.yaml 2>/dev/null; true

# Inject a minimal SOUL.md
RUN echo "You are Hermes, an AI assistant by Nous Research." > /root/.hermes/SOUL.md

# Copy our web app
COPY gateway/app.py /app/app.py
COPY gateway/static/ /app/static/
COPY gateway/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
