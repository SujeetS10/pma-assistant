FROM python:3.11-slim
WORKDIR /srv/backend
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data HF_HOME=/data/hf-cache
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /srv/backend/
COPY frontend/ /srv/frontend/
# config.py resolves the repo root two levels above app/, i.e. /srv, so frontend is at /srv/frontend
EXPOSE 8000
CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
