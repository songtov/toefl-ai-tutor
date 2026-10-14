# toefl-ai-tutor

AI-powered TOEFL Writing practice with prebuilt tasks, rubric-based feedback, and sentence-level corrections.
The current MVP shows fixed sets of three **Write an Email** tasks from a task bank and saves answers and feedback for review.

## Layout

```
backend/            FastAPI + SQLModel, DDD layers
  app/domain/          task, assessment schemas, rubric
  app/content/         task bank (JSONL): Email tasks and sets, Build a Sentence, Academic Discussion
  app/application/     LLMProvider port, tools, agent loop
  app/infrastructure/  Sign in with ChatGPT, ChatGPT plan and OpenAI API providers, database tables
  app/interfaces/      HTTP API
frontend/           Next.js UI, proxies /api/* to the backend
```

## Run with Docker

The default provider, `chatgpt_plan`, uses your ChatGPT plan through
[Sign in with ChatGPT for open-source and locally hosted apps](https://developers.openai.com/siwc/token-sharing-open-source) (preview).

```text
Browser -> Next.js (127.0.0.1:3000) -> FastAPI (127.0.0.1:1455) -> OpenAI Responses API (your ChatGPT plan)
```

```sh
cp backend/.env.example backend/.env   # set CHATGPT_MODEL and TOKEN_ENCRYPTION_KEY (see the file)
docker compose up -d --build
```

Open http://127.0.0.1:3000 (not `localhost`, so the sign-in cookies match the callback), choose **Continue with ChatGPT**, and approve access.
Signing in creates your account: the app keeps your ChatGPT account ID and email, and your sets are visible only to you.
OpenAI redirects back to `http://127.0.0.1:1455/auth/callback`, which Docker forwards to the backend container, so the sign-in must happen in a browser on the same machine.
The database and credentials live in the `tutor-data` volume and survive restarts; `docker compose down -v` deletes them.
Databases created before accounts or the task bank were added are not migrated: run `docker compose down -v` (or delete `tutor.db`) once.

`docker-compose.yml` is the development setup: `backend/app` and `frontend` are mounted into the containers, uvicorn runs with `--reload`, and the frontend runs `next dev`, so edits apply without rebuilding.
After changing dependencies (`pyproject.toml`, `package.json`), run `docker compose up -d --build -V` to rebuild and refresh `node_modules`.

## Run without Docker

Backend (Python 3.12+, [uv](https://docs.astral.sh/uv/)). The OAuth callback is `http://127.0.0.1:<OAUTH_CALLBACK_PORT>/auth/callback`, so run the backend on that port (default 1455):

```sh
cd backend
cp .env.example .env
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1455 --no-access-log
```

Frontend (Node 20+):

```sh
cd frontend
npm install
API_URL=http://127.0.0.1:1455 npm run dev   # http://127.0.0.1:3000
```

API only (write requests must send `content-type: application/json`):

```sh
curl 127.0.0.1:1455/sets
curl -X POST 127.0.0.1:1455/sets/1/session -H 'content-type: application/json'
curl 127.0.0.1:1455/sessions/1/next
curl -X POST 127.0.0.1:1455/tasks/1/answer -H 'content-type: application/json' \
  -d '{"text": "Dear Ms. Park, ..."}'
```

## Security

- Accounts come from Sign in with ChatGPT, identified by the ChatGPT account ID (`sub`), not the email. The browser holds only an httpOnly session cookie (30 days); the database stores its SHA-256 hash.
- ChatGPT tokens stay in the backend and never reach the browser. Each user's tokens are stored in the database encrypted with `TOKEN_ENCRYPTION_KEY` (Fernet). Store the key separately from the database. `CHATGPT_AUTH_DIR` (`/data/auth` in Docker) holds the host ID with owner-only permissions (`0700` directory, `0600` file).
- Sign-in uses PKCE (S256), single-use `state` with a 10-minute expiry bound to the browser that started it, and an ID token verified against OpenAI's JWKS (issuer, audience, expiry, nonce). Inference requires the `chatgpt.tokens.use.direct` scope.
- Refresh tokens rotate; refreshes are serialized. **Sign out** revokes the refresh token, clears your tokens, and ends the session. The browser remembers the last account (encrypted cookie) so signing in again reuses its ChatGPT registration.
- The API accepts only `Host` values `127.0.0.1`, `localhost`, or `backend` (DNS rebinding) and only JSON write requests (CSRF). Docker publishes both ports on `127.0.0.1` only, and the frontend applies the same `Host` check.
- To cut off access from ChatGPT's side, disconnect the app in ChatGPT Settings.

Alternatively, set `LLM_PROVIDER=openai_api`, `OPENAI_API_KEY`, and `OPENAI_MODEL` in `backend/.env` to use an API key instead of your ChatGPT plan.
The preview covers open-source and locally hosted apps; OpenAI directs paid or remotely hosted apps to an interest form.

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
