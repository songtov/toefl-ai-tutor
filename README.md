# toefl-ai-tutor

AI-powered TOEFL Writing practice with generated prompts, rubric-based feedback, and sentence-level corrections.
The current MVP generates sets of three **Write an Email** tasks and saves answers and feedback for review.

## Layout

```
backend/            FastAPI + SQLModel, DDD layers
  app/domain/          task, assessment schemas, rubric
  app/application/     LLMProvider port, tools, agent loop
  app/infrastructure/  Sign in with ChatGPT, ChatGPT plan and OpenAI API providers, database tables
  app/interfaces/      HTTP API
frontend/           Next.js UI, proxies /api/* to the backend
```

## Run locally

The default provider, `chatgpt_plan`, uses your ChatGPT plan through
[Sign in with ChatGPT for open-source and locally hosted apps](https://developers.openai.com/siwc/token-sharing-open-source) (preview).

```text
Browser -> Next.js -> FastAPI (127.0.0.1:1455) -> OpenAI Responses API (your ChatGPT plan)
```

Backend prerequisites: Python 3.12+ and [uv](https://docs.astral.sh/uv/).
The OAuth callback must be `http://127.0.0.1:<OAUTH_CALLBACK_PORT>/auth/callback`, so run the backend on that port (default 1455):

```sh
cd backend
cp .env.example .env   # set CHATGPT_MODEL to a model available to your ChatGPT account
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 1455
```

Sign in once (a UI button is planned; until then, use the API):

```sh
curl -s -X POST 127.0.0.1:1455/auth/login -H 'content-type: application/json' | jq -r .authorize_url
# open the URL, approve, and you are redirected back to FRONTEND_URL with ?auth=ok
curl -s 127.0.0.1:1455/auth/status
```

Frontend (Node 20+):

```sh
cd frontend
npm install
API_URL=http://127.0.0.1:1455 npm run dev   # http://127.0.0.1:3000
```

API only (write requests must send `content-type: application/json`):

```sh
curl -X POST 127.0.0.1:1455/sessions -H 'content-type: application/json'
curl 127.0.0.1:1455/sessions/1/next
curl -X POST 127.0.0.1:1455/tasks/1/answer -H 'content-type: application/json' \
  -d '{"text": "Dear Ms. Park, ..."}'
```

## Security

- Tokens stay in the backend: `CHATGPT_AUTH_DIR` holds `credentials.json` and `host_id` with owner-only permissions (`0700` directory, `0600` files). Never commit or share this directory.
- Sign-in uses PKCE (S256), single-use `state` with a 10-minute expiry, and an ID token verified against OpenAI's JWKS (issuer, audience, expiry, nonce). Inference requires the `chatgpt.tokens.use.direct` scope.
- Refresh tokens rotate; refreshes are serialized. Sign out (`POST /auth/logout`) revokes the refresh token and clears local tokens.
- The API has no user accounts. It accepts only `Host` values `127.0.0.1`, `localhost`, or `backend` (DNS rebinding) and only JSON write requests (CSRF). Keep it bound to `127.0.0.1`; anyone who can reach it can use your plan.
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
