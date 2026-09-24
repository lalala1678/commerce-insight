FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY sql sql
COPY sample_data sample_data
COPY scripts scripts
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
