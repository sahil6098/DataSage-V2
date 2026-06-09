# ── Base image ────────────────────────────────────────────────
FROM python:3.11-slim

# System deps needed for psycopg and cryptography wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 1. Install CPU-only PyTorch FIRST (prevents sentence-transformers
#        from pulling the 2 GB CUDA version automatically) ──────────
RUN pip install --no-cache-dir \
    torch==2.2.2+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# ── 2. Install the rest of requirements ───────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 3. Copy app source ────────────────────────────────────────
COPY . .

# Create upload directory
RUN mkdir -p storage/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
