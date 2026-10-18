# Build from the REPO ROOT:  docker build -f task3-meeting-to-sow/Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/shared:/app/task3-meeting-to-sow
WORKDIR /app/task3-meeting-to-sow
COPY task3-meeting-to-sow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY task3-meeting-to-sow /app/task3-meeting-to-sow
EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8003/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8003"]
