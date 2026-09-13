import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from household_imap.auth import JWTVerifier
from household_imap.mail import MailService
from household_imap.server import build_server, make_app


@pytest.fixture
def signed(auth_config):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = JWTVerifier(auth_config)
    verifier.keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key()))
    def token(**overrides):
        claims = dict(iss=auth_config.issuer, aud=auth_config.resource, sub="owner", azp="chatgpt-client",
                      scope="mail:read", iat=int(time.time()) - 1, exp=int(time.time()) + 300)
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test"})
    return verifier, token


def test_valid_token(signed):
    verifier, token = signed
    result = verifier.verify(token())
    assert result.subject == "owner" and result.resource == "https://mail.example.com/mcp"


@pytest.mark.parametrize("claims", [dict(iss="https://evil.invalid/"), dict(aud="some-other-api"),
    dict(sub="another-user"), dict(azp="another-client"), dict(scope="mail:write"),
    dict(exp=1), dict(iat=9999999999), dict(scope=[]), dict(sub=["owner"])])
def test_invalid_tokens_rejected(signed, claims):
    verifier, token = signed
    assert verifier.verify(token(**claims)) is None


def test_unsigned_and_bad_signature(signed):
    verifier, token = signed
    assert verifier.verify("not-a-token") is None
    assert verifier.verify(token()[:-10] + "x" * 10) is None
    assert verifier.verify(jwt.encode({"sub": "owner"}, "", algorithm="none")) is None


def test_http_auth_discovery_and_tools(mail_config, auth_config, signed):
    verifier, token = signed
    mcp = build_server(mail_config, auth_config, verifier=verifier)
    with TestClient(make_app(mcp, auth_config), base_url="https://mail.example.com") as client:
        denied = client.post("/mcp", json={})
        assert denied.status_code == 401
        assert "resource_metadata=" in denied.headers["www-authenticate"]
        metadata = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert metadata["resource"] == auth_config.resource
        assert metadata["authorization_servers"] == [auth_config.issuer]
        assert client.get("/healthz").json() == {"status": "ok"}
        headers = {"Authorization": "Bearer " + token(), "Accept": "application/json, text/event-stream"}
        init = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        assert init.status_code == 200, init.text
        result = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert result.status_code == 200, result.text
        tools = result.json()["result"]["tools"]
        assert len(tools) == 7
        assert all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"] for t in tools)
        assert all(t["_meta"]["securitySchemes"][0]["scopes"] == ["mail:read", "offline_access"] for t in tools)
        call = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "list_accounts", "arguments": {}}})
        assert call.status_code == 200 and "personal" in call.text and "hidden" not in call.text
        assert call.headers["cache-control"] == "no-store"
        wrong = client.post("/mcp", headers={**headers, "Authorization": "Bearer " + token(sub="intruder")}, json={})
        assert wrong.status_code == 401
        host = client.post("/mcp", headers={**headers, "Host": "attacker.invalid"}, json={})
        assert host.status_code in (400, 421)
        origin = client.post("/mcp", headers={**headers, "Origin": "https://attacker.invalid"}, json={})
        assert origin.status_code == 403
