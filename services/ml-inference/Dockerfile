FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8001
CMD ["gunicorn", "--bind", "0.0.0.0:8001", "--workers", "2", "--threads", "4", "--timeout", "60", "app:app"]