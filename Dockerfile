# Use an official Python runtime as a parent image
FROM python:3.12 

# Set the working directory in the container
WORKDIR /src

# Copy the current directory contents into the container at /app
COPY requirements.txt . 

# Install any needed packages specified in requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ . 
COPY data/ ./data/
CMD ["python", "local_ingestion.py"]