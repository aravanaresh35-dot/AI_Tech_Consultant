# Build from the REPO ROOT:  docker build -f task1-knowledge-brain/Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/shared:/app/task1-knowledge-brain
WORKDIR /app/task1-knowledge-brain
COPY task1-knowledge-brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY task1-knowledge-brain /app/task1-knowledge-brain
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8001/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
