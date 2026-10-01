from mcp.server.mcpserver import MCPServer

# Cria o servidor. O nome aparece para a IA quando ela lista os servidores.
mcp = MCPServer("meu-mcp")


# Cada função marcada com @mcp.tool() vira uma ferramenta que a IA pode chamar.
# A docstring explica para a IA o que a ferramenta faz; os tipos (int, str)
# dizem quais argumentos ela precisa mandar.
@mcp.tool()
def somar(a: int, b: int) -> int:
    """Soma dois números inteiros."""
    return a + b


@mcp.tool()
def contar_palavras(texto: str) -> int:
    """Conta quantas palavras tem um texto."""
    return len(texto.split())


if __name__ == "__main__":
    # Roda o servidor via stdio: a IA conversa com ele pela entrada/saída do processo.
    mcp.run()
