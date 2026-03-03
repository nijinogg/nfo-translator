FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev gcc
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
# Run uvicorn on port 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]