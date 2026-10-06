# english-ai-tutor

An AI English tutor that remembers learner weaknesses and plans the next lesson. The MVP targets TOEFL Writing.
Sprint 1 covers one flow: generate a **Write an Email** task, then score and correct the learner's answer.

## Layout

```
backend/            FastAPI + SQLModel, DDD layers
  app/domain/          task, assessment schemas, rubric
  app/application/     LLMProvider port, tools, agent loop
  app/infrastructure/  OpenAI provider, database tables
  app/interfaces/      HTTP API
frontend/           Next.js UI, proxies /api/* to the backend
```

## Run locally

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```sh
cd backend
cp .env.example .env   # defaults to the Codex CLI provider: run `codex login` once
uv run uvicorn app.main:app --reload --port 8000
```

Frontend with Docker, proxying to the local backend:

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
