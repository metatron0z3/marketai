FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set PYTHONPATH so `from collectors.xxx import` works
ENV PYTHONPATH=/app

CMD ["prefect", "worker", "start", "--pool", "default", "--type", "process"]
