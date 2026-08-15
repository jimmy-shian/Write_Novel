FROM python:3.10-slim

# Create a non-root user (UID 1000 is required/recommended by Hugging Face Spaces)
RUN useradd -m -u 1000 user

WORKDIR /app

# Install system dependencies if required for build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and grant permissions to user 1000
COPY --chown=user:user . .

# Ensure data directory exists with write permissions for SQLite database
RUN mkdir -p /app/data && chown -R user:user /app

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-7860}"]