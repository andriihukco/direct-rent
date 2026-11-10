FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY directrent ./directrent
COPY migrations ./migrations
COPY scripts ./scripts
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "--no-sync", "python", "-m", "directrent.main"]
