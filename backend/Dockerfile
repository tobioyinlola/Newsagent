FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen || uv sync --no-dev
COPY . .
ENV PATH="/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
# Release step (Alembic) runs before the API starts; see railway.toml.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
