FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml ./
COPY apps/api/energy_manager ./energy_manager
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
RUN pip install --no-cache-dir .
COPY packages /packages
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn energy_manager.main:app --host 0.0.0.0 --port 8000"]
