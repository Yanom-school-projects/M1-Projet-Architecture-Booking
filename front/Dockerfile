FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Utilisateur sans privilèges ; HOME pour le cache de configuration Streamlit.
RUN useradd --system --uid 10001 --create-home front
USER front

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
