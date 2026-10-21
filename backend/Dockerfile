FROM python:3.11-slim
WORKDIR /srv/backend
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data MODEL_CACHE_DIR=/srv/model_cache OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=2
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /srv/backend/
COPY frontend/ /srv/frontend/
# Bake the embedding model into the image (outside /data, which is a volume at runtime).
RUN python -m scripts.prefetch_model
# config.py resolves the repo root two levels above app/, i.e. /srv, so frontend is at /srv/frontend
EXPOSE 8000
CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--workers", "1"]
