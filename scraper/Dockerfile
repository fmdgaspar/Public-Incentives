FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application code
COPY scraper/ ./scraper/

# Create data directories
RUN mkdir -p /data/raw /data/processed /cache

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV RAW_DATA_DIR=/data/raw
ENV PROCESSED_DATA_DIR=/data/processed

CMD ["python", "-m", "scraper.run"]

