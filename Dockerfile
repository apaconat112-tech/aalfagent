FROM python:3.11-slim

WORKDIR /app

# System dependencies for SQLite and SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Run the Telegram bot in long-polling mode.
CMD ["python", "bot.py"]
