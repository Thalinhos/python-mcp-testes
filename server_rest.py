import hmac
import json
import os

import uvicorn
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from starlette.responses import JSONResponse, PlainTextResponse

load_dotenv()

# Mesmo servidor do server.py, mas exposto por HTTP (streamable-http) em vez de stdio.
# Assim ele roda como uma API: qualquer cliente MCP acessa pela URL, sem iniciar o processo local.
mcp = MCPServer("meu-mcp-rest")


@mcp.tool()
def somar(a: int, b: int) -> int:
    """Soma dois números inteiros."""
    return a + b


@mcp.tool()
def contar_palavras(texto: str) -> int:
    """Conta quantas palavras tem um texto."""
    return len(texto.split())


# --- Autenticação -----------------------------------------------------------
# As chaves válidas vêm da variável MCP_API_KEYS (separadas por vírgula), o que permite
# ter uma chave por cliente e revogar uma sem derrubar as outras.
def carregar_chaves() -> list[str]:
    chaves = [c.strip() for c in os.environ.get("MCP_API_KEYS", "").split(",") if c.strip()]
    if not chaves:
        raise SystemExit(
            "Defina MCP_API_KEYS (uma ou mais chaves separadas por vírgula) no ambiente ou no .env."
        )
    return chaves


class BearerAuthMiddleware:
    """Exige 'Authorization: Bearer <chave>' em toda requisição, exceto /health.

    É um middleware ASGI puro (e não BaseHTTPMiddleware) para não quebrar o streaming SSE.
    """

    def __init__(self, app, chaves: list[str]):
        self.app = app
        self.chaves = chaves

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        scheme, _, token = auth.partition(" ")

        # compare_digest evita ataques de timing; percorremos todas as chaves de propósito.
        valido = scheme.lower() == "bearer" and any(
            [hmac.compare_digest(token.encode(), c.encode()) for c in self.chaves]
        )
        if not valido:
            resposta = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="meu-mcp-rest"'},
            )
            return await resposta(scope, receive, send)

        return await self.app(scope, receive, send)


def criar_app():
    # STATELESS=1 não guarda sessão na memória: necessário com vários workers/instâncias.
    app = mcp.streamable_http_app(
        host=os.environ.get("HOST", "127.0.0.1"),
        stateless_http=os.environ.get("STATELESS") == "1",
    )

    async def health(request):
        return PlainTextResponse("ok")

    app.add_route("/health", health)
    app.add_middleware(BearerAuthMiddleware, chaves=carregar_chaves())
    return app


if __name__ == "__main__":
    # O endpoint fica em http://<host>:<porta>/mcp ; /health é público (para load balancers).
    uvicorn.run(
        criar_app(),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        # Atrás de nginx/Caddy/Cloud Run, descomente para respeitar X-Forwarded-*:
        # proxy_headers=True, forwarded_allow_ips="*",
    )
