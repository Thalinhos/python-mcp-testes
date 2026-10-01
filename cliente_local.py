"""Cliente MCP em Python: lista as ferramentas do server_rest.py e chama uma delas.

Uso:  python cliente_local.py
Lê MCP_URL (padrão http://127.0.0.1:8000/mcp) e MCP_API_KEY do ambiente ou do .env.
"""

import asyncio
import os

import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
CHAVE = os.environ["MCP_API_KEY"]


async def main():
    # A autenticação vai no cliente HTTP: o header é enviado em toda requisição.
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {CHAVE}"})
    async with http, streamable_http_client(URL, http_client=http) as streams:
        async with ClientSession(*streams[:2]) as session:
            await session.initialize()

            tools = await session.list_tools()
            for t in tools.tools:
                print("ferramenta:", t.name, "-", t.description)

            resultado = await session.call_tool("somar", {"a": 17, "b": 25})
            print("17 + 25 =", resultado.content[0].text)


asyncio.run(main())
