FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Utilisateur sans privilèges : une faille dans l'application ne donne pas
# les droits root dans le conteneur. /app/logs et /data (volume compose pour
# la base SQLite et les logs) lui appartiennent : Docker reprend ces droits
# à la création d'un volume nommé.
RUN useradd --system --uid 10001 --no-create-home booking \
    && mkdir -p /app/logs /data \
    && chown -R booking:booking /app/logs /data
USER booking

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
