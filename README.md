# toefl-ai-tutor

AI-powered TOEFL Writing practice with generated prompts, rubric-based feedback, and sentence-level corrections.
The current MVP generates sets of three **Write an Email** tasks and saves answers and feedback for review.

## Layout

```
backend/            FastAPI + SQLModel, DDD layers
  app/domain/          task, assessment schemas, rubric
  app/application/     LLMProvider port, tools, agent loop
  app/infrastructure/  Codex CLI and OpenAI API providers, database tables
  app/interfaces/      HTTP API
frontend/           Next.js UI, proxies /api/* to the backend
```

## Run locally

**For the default Codex CLI setup, run the backend on your local machine.**
It launches `codex exec` using the Codex installation and login available to the backend process.
The included Docker Compose configuration runs **only the frontend** and connects to that local backend; it does not install Codex or start a backend container.

```text
Browser -> Next.js (Docker or local) -> FastAPI (local) -> Codex CLI
```

Backend prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), and the [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) installed on the host and available on `PATH`.
Run from the repository root:

```sh
codex login            # complete ChatGPT sign-in on the host
codex login status
cd backend
cp .env.example .env   # LLM_PROVIDER=codex_cli by default
uv run uvicorn app.main:app --reload --port 8000
```

In a separate terminal at the repository root, start the frontend with Docker, proxying to the local backend:

```sh
docker compose up -d --build   # UI on :3000
# other ports? API_URL=http://host.docker.internal:8002 FRONTEND_PORT=3001 docker compose up -d --build
```

Or frontend without Docker (Node 20+):

```sh
cd frontend
npm install
npm run dev            # http://localhost:3000, set API_URL if the backend is not on :8000
```

API only:

```sh
curl -X POST localhost:8000/sessions
curl localhost:8000/sessions/1/next
curl -X POST localhost:8000/tasks/1/answer -H 'content-type: application/json' \
  -d '{"text": "Dear Ms. Park, ..."}'
```

## Codex authentication and Docker

The local-backend requirement above describes this repository's current setup, not a Codex limitation.
Codex supports headless sign-in with `codex login --device-auth` when device code login is enabled for the account or workspace.
OpenAI also documents transferring a login cache into a Docker container. Containerizing this backend would additionally require a Codex installation and protected credential storage; that configuration is not included or tested here.
Never commit credentials or bake them into a container image. See [Codex authentication](https://learn.chatgpt.com/docs/auth).

Third-party app authentication is a separate integration. OpenAI documents [Sign in with ChatGPT plan usage](https://developers.openai.com/siwc/token-sharing-open-source) for open-source and locally hosted apps, including [Codex app-server integration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
The documentation directs paid or remotely hosted apps to an interest form. This project currently implements neither that OAuth flow nor per-user credential management; it uses the local operator's Codex login.

Alternatively, set `LLM_PROVIDER=openai_api`, `OPENAI_API_KEY`, and `OPENAI_MODEL` in `backend/.env` to use the existing API-key provider without Codex CLI.
The current MVP is single-user and has no application authentication; switching providers alone does not make it a multi-user hosted service.

## Checks

```sh
cd backend && uv run ruff check . && uv run pytest
cd frontend && npm run lint && npm run build
```

## Eval seed

After answering Email tasks, export the latest five to `backend/evals/email_seed.jsonl`:

```sh
cd backend && uv run python -m scripts.export_email_seed 5
```

## License

[MIT](LICENSE)
