FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure Poetry to not create virtual environment in container
RUN poetry config virtualenvs.create false

# Install dependencies without installing the project itself
RUN poetry install --no-root --no-interaction

# Create logs directory
RUN mkdir logs

# Copy application code
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x scripts/entrypoint.py

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Use entrypoint script to start the service
CMD ["python", "scripts/entrypoint.py"]
