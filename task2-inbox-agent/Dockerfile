# Build from the REPO ROOT:  docker build -f task2-inbox-agent/Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/shared:/app/task2-inbox-agent
WORKDIR /app/task2-inbox-agent
COPY task2-inbox-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY task2-inbox-agent /app/task2-inbox-agent
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8002/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8002"]
