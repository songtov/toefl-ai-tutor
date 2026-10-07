"""Sign in with ChatGPT for open-source/local apps: OAuth (PKCE) and local credential storage.

See https://developers.openai.com/siwc/token-sharing-open-source. Tokens never leave this module
except as a bearer credential for the Responses API.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import jwt
from pydantic import BaseModel

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
REVOKE_URL = f"{ISSUER}/api/accounts/oauth/revoke"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
REGISTRATION_CLIENT_ID = "dynamic_agent_client"
LOGIN_TTL_S = 600
REFRESH_MARGIN_S = 300
TERMINAL_REFRESH_ERRORS = {
    "invalid_grant",
    "invalid_refresh_token",
    "token_expired",
    "refresh_token_expired",
    "refresh_token_invalidated",
    "refresh_token_reused",
}
_ERROR_CODE = re.compile(r"[a-z0-9_]{1,64}")


class AuthError(Exception):
    """Carries only an OAuth-style error code, never token material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if _ERROR_CODE.fullmatch(code) else "oauth_error"


class Credentials(BaseModel):
    client_id: str
    subject: str
    email: str = ""
    id_token: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    scopes: list[str] = []

    @property
    def signed_in(self) -> bool:
        return bool(self.access_token)

    @property
    def plan_enabled(self) -> bool:
        return PLAN_SCOPE in self.scopes

    def signed_out(self) -> "Credentials":
        # Keep the account/client mapping so the next sign-in reuses the issued client ID.
        return Credentials(client_id=self.client_id, subject=self.subject, email=self.email)


class CredentialStore:
    """Owner-only files: `host_id` (stable per host) and `credentials.json`."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        self._dir = directory

    def host_id(self) -> str:
        path = self._dir / "host_id"
        if path.exists():
            return path.read_text().strip()
        value = f"urn:uuid:{uuid.uuid4()}"
        self._write(path, value)
        return value

    def load(self) -> Credentials | None:
        path = self._dir / "credentials.json"
        return Credentials.model_validate_json(path.read_text()) if path.exists() else None

    def save(self, credentials: Credentials) -> None:
        self._write(self._dir / "credentials.json", credentials.model_dump_json())

    def _write(self, path: Path, text: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._dir)  # created with mode 0600
        try:
            with os.fdopen(fd, "w") as f:
                f.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


@dataclass(frozen=True)
class _PendingLogin:
    state: str
    nonce: str
    verifier: str
    client_id: str
    created_at: float


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _error_code(response: httpx.Response) -> str:
    try:
        error = response.json().get("error")
    except ValueError:
        error = None
    return error if isinstance(error, str) else f"http_{response.status_code}"


class ChatGPTAuth:
    def __init__(
        self,
        store: CredentialStore,
        *,
        redirect_uri: str,
        agent_name: str,
        http: httpx.Client,
        signing_key: Callable[[str], Any] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._redirect_uri = redirect_uri
        self._agent_name = agent_name
        self._http = http
        if signing_key is None:
            jwks = jwt.PyJWKClient(JWKS_URL)
            signing_key = lambda token: jwks.get_signing_key_from_jwt(token).key  # noqa: E731
        self._signing_key = signing_key
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: _PendingLogin | None = None

    def status(self) -> Credentials | None:
        return self._store.load()

    def start_login(self) -> str:
        saved = self._store.load()
        pending = _PendingLogin(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            verifier=secrets.token_urlsafe(64),
            client_id=saved.client_id if saved else REGISTRATION_CLIENT_ID,
            created_at=self._clock(),
        )
        params = {
            "client_id": pending.client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": pending.state,
            "nonce": pending.nonce,
            "code_challenge_method": "S256",
            "code_challenge": _code_challenge(pending.verifier),
            "ext_agent_host_id": self._store.host_id(),
        }
        if saved is None:
            params["agent_name_hint"] = self._agent_name
        else:
            if saved.id_token:
                params["id_token_hint"] = saved.id_token
            if saved.email:
                params["login_hint"] = saved.email
        with self._lock:
            self._pending = pending
        return f"{AUTHORIZE_URL}?{urlencode(params, quote_via=quote)}"

    def complete_login(self, params: Mapping[str, str]) -> Credentials:
        with self._lock:
            pending = self._pending
            state = params.get("state", "").encode()
            if pending is None or not hmac.compare_digest(state, pending.state.encode()):
                raise AuthError("invalid_state")
            self._pending = None
        if self._clock() - pending.created_at > LOGIN_TTL_S:
            raise AuthError("login_expired")
        if "error" in params:
            raise AuthError(params["error"])

        client_id = pending.client_id
        returned = params.get("client_id")
        if client_id == REGISTRATION_CLIENT_ID:
            if not returned or returned == REGISTRATION_CLIENT_ID:
                raise AuthError("registration_incomplete")
            client_id = returned
        elif returned and returned != client_id:
            raise AuthError("client_mismatch")
        if not params.get("code"):
            raise AuthError("missing_code")

        tokens = self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": params["code"],
                "code_verifier": pending.verifier,
                "redirect_uri": self._redirect_uri,
                "resource": RESOURCE,
            }
        )
        claims = self._verify_id_token(tokens.get("id_token", ""), client_id, pending.nonce)
        with self._lock:
            saved = self._store.load()
            if saved and saved.client_id == client_id and saved.subject != claims["sub"]:
                raise AuthError("account_mismatch")
            credentials = Credentials(
                client_id=client_id,
                subject=claims["sub"],
                email=claims.get("email", ""),
                id_token=tokens["id_token"],
                **self._token_fields(tokens),
            )
            self._store.save(credentials)
        return credentials

    def access_token(self) -> str:
        # Held across the refresh call: refresh tokens rotate, so refreshes must not race.
        with self._lock:
            saved = self._store.load()
            if saved is None or not saved.signed_in:
                raise AuthError("sign_in_required")
            if not saved.plan_enabled:
                raise AuthError("plan_not_enabled")
            if saved.expires_at - self._clock() > REFRESH_MARGIN_S:
                return saved.access_token
            if not saved.refresh_token:
                raise AuthError("sign_in_required")
            try:
                tokens = self._token_request(
                    {
                        "grant_type": "refresh_token",
                        "client_id": saved.client_id,
                        "refresh_token": saved.refresh_token,
                        "resource": RESOURCE,
                    }
                )
            except AuthError as e:
                if e.code in TERMINAL_REFRESH_ERRORS:
                    self._store.save(saved.signed_out())
                    raise AuthError("sign_in_required") from e
                raise
            refreshed = saved.model_copy(update=self._token_fields(tokens, previous=saved))
            self._store.save(refreshed)
            return refreshed.access_token

    def logout(self) -> bool:
        """Clears local tokens. Returns whether OpenAI confirmed revoking the refresh token."""
        with self._lock:
            self._pending = None
            saved = self._store.load()
            if saved is None:
                return True
            revoked = not saved.refresh_token
            if saved.refresh_token:
                try:
                    response = self._http.post(
                        REVOKE_URL,
                        data={
                            "token": saved.refresh_token,
                            "token_type_hint": "refresh_token",
                            "client_id": saved.client_id,
                        },
                    )
                    revoked = response.status_code == 200
                except httpx.HTTPError:
                    revoked = False
            self._store.save(saved.signed_out())
            return revoked

    def _token_request(self, form: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._http.post(TOKEN_URL, data=form)
        except httpx.HTTPError as e:
            raise AuthError("token_endpoint_unreachable") from e
        if response.status_code != 200:
            raise AuthError(_error_code(response))
        try:
            tokens = response.json()
        except ValueError as e:
            raise AuthError("invalid_token_response") from e
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            raise AuthError("invalid_token_response")
        return tokens

    def _token_fields(
        self, tokens: dict[str, Any], previous: Credentials | None = None
    ) -> dict[str, Any]:
        scope = tokens.get("scope")
        refresh_token = tokens.get("refresh_token") or (previous.refresh_token if previous else "")
        return {
            "access_token": tokens["access_token"],
            "refresh_token": refresh_token,
            "expires_at": self._clock() + float(tokens.get("expires_in", 0)),
            "scopes": scope.split() if scope else (previous.scopes if previous else []),
        }

    def _verify_id_token(self, token: str, client_id: str, nonce: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self._signing_key(token),
                algorithms=["RS256"],
                audience=client_id,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as e:
            raise AuthError("invalid_id_token") from e
        if not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
            raise AuthError("invalid_id_token")
        return claims
