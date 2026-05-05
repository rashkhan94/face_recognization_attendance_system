FROM python:3.11-slim

# Install system dependencies for dlib/face_recognition
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libboost-all-dev \
    libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Initialize database on first run
ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120"]
