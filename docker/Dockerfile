# Base Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pymongo==4.3.3 \
    pydantic==1.10.8 \
    cryptography==41.0.1

# Copy the rest of the application
COPY . .

# Create necessary directories if they don't exist
RUN mkdir -p /app/logs /app/data

# Expose port
EXPOSE 8000

# Create a non-root user and switch to it
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden in docker-compose.yml)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"] 