import anyio
import jwt
from mcp.server.auth.provider import AccessToken

from .config import AuthConfig

SCOPE = "mail:read"


class JWTVerifier:
    """Trust only the configured issuer, API audience, owner and OAuth client."""

    def __init__(self, config: AuthConfig):
        self.config = config
        self.keys = jwt.PyJWKClient(config.jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)
        self.limiter = anyio.CapacityLimiter(2)

    def verify(self, token):
        if len(token) > 16384:
            return None
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.config.resource,
                                issuer=self.config.issuer,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
            subject = claims["sub"]
            client = claims.get("azp") or claims.get("client_id")
            scopes = claims.get("scope", "").split()
            if subject not in self.config.allowed_subjects or client not in self.config.allowed_client_ids or SCOPE not in scopes:
                return None
            return AccessToken(token=token, client_id=client, subject=subject, scopes=scopes,
                               expires_at=int(claims["exp"]), resource=self.config.resource)
        except Exception:
            # Never log bearer tokens, decoded claims or provider exception messages.
            return None

    async def verify_token(self, token: str):
        return await anyio.to_thread.run_sync(self.verify, token, limiter=self.limiter)

