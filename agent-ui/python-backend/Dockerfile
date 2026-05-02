FROM python:3.11-slim

WORKDIR /app

# System dependencies required by torch, spaCy, and transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model (small, ~10 MB — bake into image)
RUN python -m spacy download en_core_web_sm

# Copy application source
COPY . .

# ML model weights are large (several GB). Mount a host volume at /app/models
# so they are downloaded once and reused across container restarts.
ENV MODEL_CACHE_DIR=/app/models
ENV TRANSFORMERS_CACHE=/app/models/transformers
ENV HF_HOME=/app/models/hf

EXPOSE 8003

CMD ["python", "app/main.py"]
