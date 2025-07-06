FROM python:3.12-slim

WORKDIR /src

# Copy source code and requirements
COPY src/ .
COPY requirements.txt .

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libc6-dev \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# The file is now at /src/local_ingestion.py (not /src/src/local_ingestion.py)
CMD ["python", "local_ingestion.py"]