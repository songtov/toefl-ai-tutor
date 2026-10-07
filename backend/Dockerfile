FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
# Non-root; /data (DB + OAuth credentials) is the only writable path and lives in a volume.
RUN useradd --system --uid 10001 app && mkdir -m 700 /data && chown app /data
USER app
ENV PATH=/app/.venv/bin:$PATH DATABASE_URL=sqlite:////data/tutor.db CHATGPT_AUTH_DIR=/data/auth
EXPOSE 8000
# No access log: the OAuth callback URL carries the authorization code.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
