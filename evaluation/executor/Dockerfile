FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ARG SOURCE_REVISION

LABEL org.opencontainers.image.source="https://github.com/gmoigneu/agentic-engineering-lab" \
    org.opencontainers.image.revision="${SOURCE_REVISION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 600 --retries 10 . pytest==8.3.5 ruff==0.8.6

USER 65532:65532
