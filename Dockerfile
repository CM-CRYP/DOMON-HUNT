# Utiliser une image officielle Python 3.10
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Installer dépendances avant de copier tout (cache Docker)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . /app

# curl pour le HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Healthcheck local : http://127.0.0.1:$PORT/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
 CMD curl -fsS http://127.0.0.1:$PORT/health || exit 1

# Lancer ton bot + serveur Flask (via main.py)
CMD ["python", "main.py"]
