import base64
import hashlib
import stat
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.infrastructure.chatgpt_auth import (
    ISSUER,
    LOGIN_TTL_S,
    REGISTRATION_CLIENT_ID,
    REVOKE_URL,
    SCOPES,
    AuthError,
    ChatGPTAuth,
    CredentialStore,
)

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLIENT_ID = "oaiapp_123"
NOW = time.time()


class FakeOpenAI:
    """Stands in for auth.openai.com's token and revocation endpoints."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.nonce = ""
        self.claims: dict = {}
        self.key = KEY
        self.scope = SCOPES
        self.token_error: tuple[int, dict] | None = None
        self.counter = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.requests.append((str(request.url), form))
        if str(request.url) == REVOKE_URL:
            return httpx.Response(200)
        if self.token_error:
            return httpx.Response(self.token_error[0], json=self.token_error[1])
        self.counter += 1
        claims = {
            "iss": ISSUER,
            "aud": form["client_id"],
            "sub": "user-1",
            "email": "me@example.com",
            "iat": int(NOW),
            "exp": int(NOW) + 3600,
            "nonce": self.nonce,
            **self.claims,
        }
        return httpx.Response(
            200,
            json={
                "access_token": f"access-{self.counter}",
                "refresh_token": f"refresh-{self.counter}",
                "id_token": jwt.encode(claims, self.key, algorithm="RS256"),
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": self.scope,
            },
        )


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def server() -> FakeOpenAI:
    return FakeOpenAI()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path) -> CredentialStore:
    return CredentialStore(tmp_path / "auth")


@pytest.fixture
def auth(store, server, clock) -> ChatGPTAuth:
    return ChatGPTAuth(
        store,
        redirect_uri="http://127.0.0.1:1455/auth/callback",
        agent_name="toefl-ai-tutor",
        http=httpx.Client(transport=httpx.MockTransport(server.handle)),
        signing_key=lambda token: KEY.public_key(),
        clock=clock,
    )


def start(auth: ChatGPTAuth, server: FakeOpenAI) -> dict[str, str]:
    url = auth.start_login()
    params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    server.nonce = params["nonce"]
    return params


def sign_in(auth: ChatGPTAuth, server: FakeOpenAI):
    params = start(auth, server)
    return auth.complete_login({"code": "c", "state": params["state"], "client_id": CLIENT_ID})


def test_first_login_registers_with_pkce(auth, server, store):
    url = auth.start_login()
    assert url.startswith("https://auth.openai.com/api/accounts/authorize?")
    assert "+" not in url
    params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert params["client_id"] == REGISTRATION_CLIENT_ID
    assert params["agent_name_hint"] == "toefl-ai-tutor"
    assert params["ext_agent_host_id"] == store.host_id()
    assert params["scope"] == SCOPES
    assert params["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    assert "id_token_hint" not in params

    server.nonce = params["nonce"]
    auth.complete_login({"code": "c", "state": params["state"], "client_id": CLIENT_ID})
    _, form = server.requests[0]
    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert params["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert params["code_challenge_method"] == "S256"
    assert form["client_id"] == CLIENT_ID
    assert form["redirect_uri"] == params["redirect_uri"]
    assert form["resource"] == "https://api.openai.com/v1"


def test_login_saves_credentials_owner_only(auth, server, store, tmp_path):
    credentials = sign_in(auth, server)
    assert credentials.client_id == CLIENT_ID
    assert credentials.subject == "user-1"
    assert credentials.plan_enabled
    assert store.load() == credentials
    assert stat.S_IMODE((tmp_path / "auth").stat().st_mode) == 0o700
    for name in ("credentials.json", "host_id"):
        assert stat.S_IMODE((tmp_path / "auth" / name).stat().st_mode) == 0o600
    assert {p.name for p in (tmp_path / "auth").iterdir()} == {"credentials.json", "host_id"}


def test_host_id_is_stable(store, tmp_path):
    host_id = store.host_id()
    assert host_id.startswith("urn:uuid:")
    assert CredentialStore(tmp_path / "auth").host_id() == host_id


def test_reauth_reuses_client_id_and_hints(auth, server):
    first = sign_in(auth, server)
    params = start(auth, server)
    assert params["client_id"] == CLIENT_ID
    assert params["id_token_hint"] == first.id_token
    assert params["login_hint"] == "me@example.com"
    assert "agent_name_hint" not in params
    auth.complete_login({"code": "c", "state": params["state"]})


@pytest.mark.parametrize(
    "callback, code",
    [
        ({"state": "wrong"}, "invalid_state"),
        ({"state": "é"}, "invalid_state"),
        ({"error": "access_denied"}, "access_denied"),
        ({"code": "c"}, "registration_incomplete"),
        ({"code": "c", "client_id": REGISTRATION_CLIENT_ID}, "registration_incomplete"),
        ({"client_id": CLIENT_ID}, "missing_code"),
    ],
)
def test_bad_callback_rejected_without_exchange(auth, server, store, callback, code):
    params = start(auth, server)
    with pytest.raises(AuthError) as e:
        auth.complete_login({"state": params["state"], **callback})
    assert e.value.code == code
    assert server.requests == []
    assert store.load() is None


def test_state_is_single_use_and_expires(auth, server, clock):
    params = start(auth, server)
    callback = {"code": "c", "state": params["state"], "client_id": CLIENT_ID}
    auth.complete_login(callback)
    with pytest.raises(AuthError, match="invalid_state"):
        auth.complete_login(callback)

    params = start(auth, server)
    clock.now += LOGIN_TTL_S + 1
    with pytest.raises(AuthError, match="login_expired"):
        auth.complete_login({"code": "c", "state": params["state"]})


def test_reauth_rejects_other_client_id(auth, server):
    sign_in(auth, server)
    params = start(auth, server)
    with pytest.raises(AuthError, match="client_mismatch"):
        auth.complete_login({"code": "c", "state": params["state"], "client_id": "oaiapp_x"})


@pytest.mark.parametrize(
    "tamper",
    [
        lambda s: setattr(s, "key", OTHER_KEY),
        lambda s: s.claims.update(aud="oaiapp_other"),
        lambda s: s.claims.update(iss="https://evil.example"),
        lambda s: s.claims.update(nonce="replayed"),
        lambda s: s.claims.update(exp=int(NOW) - 10),
    ],
    ids=["signature", "audience", "issuer", "nonce", "expired"],
)
def test_invalid_id_token_rejected(auth, server, store, tamper):
    tamper(server)
    params = start(auth, server)
    with pytest.raises(AuthError, match="invalid_id_token"):
        auth.complete_login({"code": "c", "state": params["state"], "client_id": CLIENT_ID})
    assert store.load() is None


def test_reauth_with_other_account_rejected(auth, server, store):
    first = sign_in(auth, server)
    server.claims["sub"] = "user-2"
    params = start(auth, server)
    with pytest.raises(AuthError, match="account_mismatch"):
        auth.complete_login({"code": "c", "state": params["state"]})
    assert store.load() == first


def test_without_plan_scope_no_access_token(auth, server):
    server.scope = "openid profile email offline_access"
    credentials = sign_in(auth, server)
    assert credentials.signed_in and not credentials.plan_enabled
    with pytest.raises(AuthError, match="plan_not_enabled"):
        auth.access_token()


def test_access_token_refreshes_and_rotates(auth, server, store, clock):
    sign_in(auth, server)
    assert auth.access_token() == "access-1"
    clock.now += 3600 - 60
    assert auth.access_token() == "access-2"
    _, form = server.requests[-1]
    assert form == {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": "refresh-1",
        "resource": "https://api.openai.com/v1",
    }
    saved = store.load()
    assert (saved.refresh_token, saved.expires_at) == ("refresh-2", clock.now + 3600)


def test_terminal_refresh_error_signs_out(auth, server, store, clock):
    sign_in(auth, server)
    clock.now += 3600
    server.token_error = (400, {"error": "refresh_token_reused"})
    with pytest.raises(AuthError, match="sign_in_required"):
        auth.access_token()
    saved = store.load()
    assert not saved.signed_in and saved.client_id == CLIENT_ID


def test_transient_refresh_error_keeps_credentials(auth, server, store, clock):
    credentials = sign_in(auth, server)
    clock.now += 3600
    server.token_error = (503, {"detail": "unavailable"})
    with pytest.raises(AuthError, match="http_503"):
        auth.access_token()
    assert store.load() == credentials


def test_logout_revokes_and_keeps_registration(auth, server, store):
    sign_in(auth, server)
    assert auth.logout() is True
    url, form = server.requests[-1]
    assert url == REVOKE_URL
    assert form == {
        "token": "refresh-1",
        "token_type_hint": "refresh_token",
        "client_id": CLIENT_ID,
    }
    saved = store.load()
    assert not saved.signed_in and not saved.refresh_token and not saved.id_token
    assert (saved.client_id, saved.email) == (CLIENT_ID, "me@example.com")
    params = start(auth, server)
    assert params["client_id"] == CLIENT_ID and "id_token_hint" not in params


def test_error_codes_are_sanitized():
    assert AuthError("<script>alert(1)</script>").code == "oauth_error"
    assert AuthError("access_denied").code == "access_denied"
