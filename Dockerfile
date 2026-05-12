FROM python:3.11-slim

# Dépendances système : libreoffice pour la conversion PDF, fonts pour les accents
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        fonts-dejavu \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# gunicorn pour servir Flask en production
# Timeout 600s pour absorber les gros uploads (jusqu'à 200 Mo) +
# extraction PyMuPDF qui peut prendre plusieurs minutes.
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 600 app:app
