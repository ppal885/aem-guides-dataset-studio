# AEM Guides Dataset Studio - Backend
FROM python:3.12-slim

WORKDIR /app

# Install system deps (for psycopg2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data dir for SQLite (when used)
RUN mkdir -p /app/data /app/logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start uvicorn (production uses DATABASE_URL from env, typically PostgreSQL)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
