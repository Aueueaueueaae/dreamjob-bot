FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py bot.py config.py handlers.py hh_client.py models.py search.py storage.py ui.py ./
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
