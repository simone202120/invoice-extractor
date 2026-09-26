FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so code changes do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY samples ./samples
COPY .streamlit ./.streamlit
RUN uv sync --locked --no-dev

RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000 8501
CMD ["uvicorn", "invoice_extractor.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
