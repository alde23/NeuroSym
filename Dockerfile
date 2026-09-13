# Use lightweight official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and project files
COPY pyproject.toml .
COPY master_schema.json .
COPY README.md .
COPY neurosym/ neurosym/
COPY data/ data/

# Install dependencies using pip
RUN pip install --no-cache-dir -e .

# Expose server port
EXPOSE 8080

# Run NeuroSym FastAPI service
CMD ["python", "-m", "neurosym.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
