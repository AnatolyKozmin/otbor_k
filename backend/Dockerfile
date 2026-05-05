FROM python:3.12-slim

WORKDIR /app

# Зависимости отдельным слоем — переустанавливаются только при изменении requirements.txt
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Копируем только код. credentials.json и SQLite-БД подаются через volumes,
# чтобы не запекать чувствительные данные в образ.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
