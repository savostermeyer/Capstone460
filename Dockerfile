# Use Python 3.13 slim image for smaller size
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for Pillow and other packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire application
COPY . .

# Expose port (Cloud Run uses PORT environment variable)
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run with gunicorn (production WSGI server)
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --timeout 600 --access-logfile - --error-logfile - expertSystem.app:app
