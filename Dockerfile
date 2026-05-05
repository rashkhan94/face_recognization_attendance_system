FROM python:3.11-slim AS builder

# Install build dependencies for dlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake pkg-config \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dlib first (heaviest package) with reduced features
ENV DLIB_NO_GUI_SUPPORT=1
ENV CMAKE_BUILD_PARALLEL_LEVEL=2
RUN pip install --no-cache-dir dlib==19.24.6

# Install remaining packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Final slim image ---
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 liblapack3 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app
COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "python init_db.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120"]
