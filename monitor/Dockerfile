FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY check.py .
RUN mkdir -p /app/logs && chmod +x check.py

CMD ["python", "-u", "check.py"]
