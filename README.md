# Guia do meu-mcp (servidor MCP via API HTTP)

Este guia explica como rodar o `server_rest.py` e usá-lo de três formas:

1. pelo **Claude Code** local;
2. por um **segundo processo seu** que chama a **API da Anthropic**;
3. por um **segundo processo seu** que chama a **API da OpenAI**.

> O que foi testado de verdade neste projeto: o servidor, a autenticação (401/200), o `/health` e o `cliente_local.py`.
> Os exemplos que chamam a API da Anthropic/OpenAI e o `claude mcp add` seguem a documentação dessas ferramentas, mas **não foram executados aqui** (exigem suas chaves). Se algo divergir, veja a seção [Problemas comuns](#10-problemas-comuns).

---

## Sumário

1. [Conceitos rápidos](#1-conceitos-rápidos)
2. [Arquivos do projeto](#2-arquivos-do-projeto)
3. [Instalação](#3-instalação)
4. [Configurando as chaves (autenticação)](#4-configurando-as-chaves-autenticação)
5. [Subindo e testando o servidor](#5-subindo-e-testando-o-servidor)
6. [Usando no Claude Code](#6-usando-no-claude-code)
7. [Usando com a API da Anthropic](#7-usando-com-a-api-da-anthropic)
8. [Usando com a API da OpenAI](#8-usando-com-a-api-da-openai)
9. [Indo para produção](#9-indo-para-produção)
10. [Problemas comuns](#10-problemas-comuns)
11. [Como adicionar novas ferramentas](#11-como-adicionar-novas-ferramentas)

---

## 1. Conceitos rápidos

**MCP (Model Context Protocol)** é um padrão para expor *ferramentas* a uma IA. Você escreve funções Python, o servidor MCP as publica, e a IA decide quando chamá-las.

Existem dois modos de transporte, e é isso que distingue os dois arquivos do projeto:

| | `server.py` | `server_rest.py` |
|---|---|---|
| Transporte | **stdio** (entrada/saída do processo) | **streamable-http** (HTTP) |
| Quem inicia o processo | o cliente (ex.: Claude Code) | você, de forma independente |
| Onde roda | sempre na máquina do cliente | em qualquer lugar com rede |
| Autenticação | não precisa | **Bearer token** |
| Vários clientes ao mesmo tempo | não | sim |

Fluxo de uma chamada com o `server_rest.py`:

```
Cliente MCP ──POST /mcp (Authorization: Bearer <chave>)──► server_rest.py
   │                                                          │
   │  initialize → tools/list → tools/call(somar, {a:1,b:2})  │
   ◄──────────────────────── resultado ───────────────────────┘
```

Quem é o "cliente MCP" muda conforme o caso:

- **Claude Code:** ele mesmo é o cliente. Conecta direto no seu servidor.
- **API da Anthropic / OpenAI (modo connector):** o cliente é a *nuvem deles*. Eles conectam no seu servidor, então a URL precisa ser **pública**.
- **API da Anthropic / OpenAI (modo loop local):** o cliente é o *seu script*. O script pega as ferramentas do servidor, entrega ao modelo e executa as chamadas que o modelo pedir. O servidor pode ficar em `localhost`.

---

## 2. Arquivos do projeto

| Arquivo | Para quê |
|---|---|
| `server.py` | Servidor MCP local (stdio), sem autenticação. |
| `server_rest.py` | Servidor MCP como API HTTP, com autenticação Bearer e `/health`. |
| `cliente_local.py` | Cliente MCP em Python (lista e chama ferramentas, com a chave). Bom para testar. |
| `.env.example` | Modelo das variáveis de ambiente. Copie para `.env`. |
| `GUIA.md` | Este arquivo. |

---

## 3. Instalação

Requisitos: Python 3.11+ (o projeto usa o SDK `mcp` 2.x).

```powershell
cd C:\Users\thalinhos\Desktop\meu-mcp

# se ainda não existir o ambiente virtual
python -m venv .venv

.venv\Scripts\Activate.ps1
pip install mcp python-dotenv
```

Os exemplos com LLM precisam, além disso, de:

```powershell
pip install anthropic   # exemplos da seção 7
pip install openai      # exemplos da seção 8
```

> Se o PowerShell bloquear o `Activate.ps1`, rode antes
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, ou chame o Python direto:
> `.venv\Scripts\python server_rest.py`.

---

## 4. Configurando as chaves (autenticação)

O servidor exige o header:

```
Authorization: Bearer <uma das chaves>
```

Sem o header, ou com chave errada, a resposta é `401` com `WWW-Authenticate: Bearer`. A única rota pública é `GET /health`.

### 4.1 Gerar uma chave

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4.2 Guardar no `.env`

```powershell
Copy-Item .env.example .env
```

Edite o `.env`:

```
MCP_API_KEYS=cole-aqui-a-chave-gerada
MCP_API_KEY=cole-aqui-a-mesma-chave
```

- `MCP_API_KEYS` (**plural**) é lida pelo **servidor**. Aceita várias chaves separadas por vírgula.
- `MCP_API_KEY` (singular) é lida pelos **clientes** (`cliente_local.py` e os exemplos deste guia).
- Se `MCP_API_KEYS` estiver vazia, o servidor **se recusa a iniciar**. Isso é intencional: evita subir aberto por esquecimento.

### 4.3 Uma chave por cliente

```
MCP_API_KEYS=chave-claude-code,chave-script-anthropic,chave-script-openai
```

Para revogar um cliente, remova a chave dele e reinicie o servidor. Os outros continuam funcionando.

### 4.4 O que a autenticação faz (e não faz)

- Compara as chaves com `hmac.compare_digest` (resistente a ataques de timing).
- É um middleware ASGI puro, para não quebrar o streaming SSE.
- **Não** limita taxa, **não** registra quem chamou o quê, **não** diferencia permissões por chave, e **não** criptografa o tráfego. Para HTTPS veja a [seção 9](#9-indo-para-produção).
- Não é OAuth. Clientes MCP que exigem o fluxo OAuth completo não funcionam com chave estática, mas todos os usos deste guia aceitam Bearer.

---

## 5. Subindo e testando o servidor

### 5.1 Subir

```powershell
.venv\Scripts\python server_rest.py
```

Variáveis opcionais:

| Variável | Padrão | Efeito |
|---|---|---|
| `HOST` | `127.0.0.1` | `0.0.0.0` aceita conexões de outras máquinas. |
| `STATELESS` | (desligado) | `1` desativa sessões em memória (vários workers/instâncias). |
| `PORT` | `8000` | Porta HTTP. |

Endpoint MCP: `http://127.0.0.1:8000/mcp`

### 5.2 Testar com curl

No PowerShell use `curl.exe` (o `curl` puro é um alias de outro comando).

```powershell
# público, sem chave
curl.exe http://127.0.0.1:8000/health
# -> ok

# sem chave: deve dar 401
curl.exe -i -X POST http://127.0.0.1:8000/mcp `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"t\",\"version\":\"1\"}}}'

# com chave: deve dar 200
curl.exe -i -X POST http://127.0.0.1:8000/mcp `
  -H "Authorization: Bearer SUA_CHAVE" `
  -H "Content-Type: application/json" `
  -H "Accept: application/json, text/event-stream" `
  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"t\",\"version\":\"1\"}}}'
```

> O header `Accept` precisa listar `application/json` **e** `text/event-stream`, senão o servidor recusa.
> As aspas escapadas (`\"`) acima são para o PowerShell. No Git Bash use aspas simples normais.

### 5.3 Testar com o cliente Python

```powershell
.venv\Scripts\python cliente_local.py
```

Saída esperada:

```
ferramenta: somar - Soma dois números inteiros.
ferramenta: contar_palavras - Conta quantas palavras tem um texto.
17 + 25 = 42
```

O `cliente_local.py` também serve de modelo para os loops locais das seções 7.2 e 8.2.

---

## 6. Usando no Claude Code

Com o servidor rodando (seção 5), registre-o no Claude Code.

### 6.1 Via linha de comando

```powershell
claude mcp add --transport http meu-mcp-rest http://127.0.0.1:8000/mcp `
  --header "Authorization: Bearer SUA_CHAVE"
```

Escopos (opção `--scope`):

| Escopo | Onde fica | Quando usar |
|---|---|---|
| `local` (padrão) | config privada, só neste projeto | uso pessoal |
| `project` | `.mcp.json` na raiz, pode ir ao git | time inteiro |
| `user` | todos os seus projetos | ferramenta que você usa sempre |

### 6.2 Via `.mcp.json` (sem deixar a chave no arquivo)

Crie `.mcp.json` na raiz do projeto:

```json
{
  "mcpServers": {
    "meu-mcp-rest": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "Authorization": "Bearer ${MCP_API_KEY}"
      }
    }
  }
}
```

O Claude Code expande `${MCP_API_KEY}` a partir das variáveis de ambiente, então o arquivo pode ser commitado sem expor a chave. Defina a variável antes de abrir o Claude Code:

```powershell
$env:MCP_API_KEY = "SUA_CHAVE"
claude
```

Na primeira vez, o Claude Code pede para você aprovar servidores definidos em `.mcp.json`.

### 6.3 Verificar e usar

Dentro do Claude Code:

- `/mcp` lista os servidores e mostra se `meu-mcp-rest` está conectado.
- Peça em linguagem natural: *"use a ferramenta somar para 17 + 25"*. O Claude pede permissão para chamar `mcp__meu-mcp-rest__somar` na primeira vez.

Pela linha de comando:

```powershell
claude mcp list              # lista e testa a conexão
claude mcp get meu-mcp-rest  # detalhes
claude mcp remove meu-mcp-rest
```

### 6.4 Se aparecer "failed" ou "needs authentication"

- `401` → chave errada ou ausente no `--header`/`.mcp.json`.
- Conexão recusada → o servidor não está rodando ou a porta é outra.
- Mudou o servidor (ferramentas novas)? Reinicie o servidor e use `/mcp` para reconectar.

---

## 7. Usando com a API da Anthropic

Há dois jeitos. Escolha conforme **onde o servidor está**:

| | 7.1 MCP connector | 7.2 Loop local |
|---|---|---|
| Quem fala com o servidor MCP | a nuvem da Anthropic | o seu script |
| Servidor precisa de URL pública | **sim (HTTPS)** | não |
| Quantidade de código | mínima | média |
| Controle sobre cada chamada | baixo | total (logs, aprovação, limites) |

Instale e configure:

```powershell
pip install anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Os exemplos usam `claude-opus-5-5`. Troque pelo modelo que preferir (ex.: `claude-sonnet-5-5`, mais barato).

### 7.1 MCP connector (a Anthropic conecta no seu servidor)

Requisitos:

- URL **pública com HTTPS**. `localhost` não funciona, porque quem conecta é a Anthropic. Para testar, use um túnel (veja 7.3).
- Servidor acessível pelo transporte streamable-http (o seu é).
- Apenas **ferramentas** (tools) do MCP são usadas nesse modo.

São necessárias **duas** peças na requisição: `mcp_servers` (onde está o servidor) e um `mcp_toolset` em `tools` (habilita as ferramentas dele). Só a primeira dá erro de validação. Usa-se a API beta com o header `mcp-client-2025-11-20`.

```python
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY

resp = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=2000,
    messages=[{
        "role": "user",
        "content": "Some 17 com 25 e conte as palavras de 'o rato roeu a roupa'. Use as ferramentas.",
    }],
    mcp_servers=[{
        "type": "url",
        "url": "https://SEU-DOMINIO-PUBLICO/mcp",
        "name": "meu-mcp-rest",
        "authorization_token": os.environ["MCP_API_KEY"],  # vira "Authorization: Bearer ..."
    }],
    tools=[{"type": "mcp_toolset", "mcp_server_name": "meu-mcp-rest"}],
    betas=["mcp-client-2025-11-20"],
)

for block in resp.content:
    if block.type == "text":
        print("Claude:", block.text)
    elif block.type == "mcp_tool_use":
        print("chamou:", block.name, block.input)
    elif block.type == "mcp_tool_result":
        print("resultado:", block.content)
```

Detalhes importantes:

- O campo `name` em `mcp_servers` e o `mcp_server_name` em `mcp_toolset` **devem ser iguais**.
- O `authorization_token` é só o token, **sem** a palavra `Bearer`: a API monta o header.
- A resposta traz blocos `mcp_tool_use` e `mcp_tool_result`. Quem executou a ferramenta foi a Anthropic, então **não** existe loop `tool_use` para você tratar.
- Para limitar as ferramentas expostas, o `mcp_toolset` aceita configuração de permitir/negar por ferramenta (consulte a documentação do MCP connector).
- Os nomes de beta mudam com o tempo. Se der erro de beta inválido, confira o valor atual na documentação do MCP connector.

### 7.2 Loop local (o seu script é o cliente MCP)

Aqui o servidor pode ficar em `localhost`. O script:

1. conecta no servidor e lista as ferramentas;
2. converte para o formato de *tools* da Anthropic;
3. conversa com o modelo; se ele pedir uma ferramenta (`stop_reason == "tool_use"`), chama o servidor MCP e devolve o resultado; repete até o modelo responder em texto.

Salve como `agente_anthropic.py`:

```python
import asyncio
import os

import anthropic
import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
CHAVE = os.environ["MCP_API_KEY"]
MODELO = "claude-opus-5-5"
PERGUNTA = "Quanto é 17 + 25? E quantas palavras tem 'o rato roeu a roupa'?"


async def main():
    llm = anthropic.AsyncAnthropic()

    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {CHAVE}"})
    async with http, streamable_http_client(URL, http_client=http) as streams:
        async with ClientSession(*streams[:2]) as mcp:
            await mcp.initialize()

            # 1) ferramentas do MCP -> formato da Anthropic
            lista = await mcp.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in lista.tools
            ]

            messages = [{"role": "user", "content": PERGUNTA}]

            # 2) loop até o modelo parar de pedir ferramentas
            for _ in range(10):  # limite de segurança
                resp = await llm.messages.create(
                    model=MODELO,
                    max_tokens=2000,
                    tools=tools,
                    messages=messages,
                )
                messages.append({"role": "assistant", "content": resp.content})

                if resp.stop_reason != "tool_use":
                    break

                # 3) executa TODAS as chamadas pedidas e devolve num único turno "user"
                resultados = []
                for bloco in resp.content:
                    if bloco.type != "tool_use":
                        continue
                    r = await mcp.call_tool(bloco.name, bloco.input)
                    texto = "".join(c.text for c in r.content if c.type == "text")
                    resultados.append({
                        "type": "tool_result",
                        "tool_use_id": bloco.id,
                        "content": texto,
                        "is_error": bool(r.isError),
                    })
                messages.append({"role": "user", "content": resultados})

            for bloco in resp.content:
                if bloco.type == "text":
                    print(bloco.text)


asyncio.run(main())
```

Pontos de atenção:

- Todos os `tool_result` de um mesmo turno vão **numa única** mensagem `user`.
- Todo `tool_use` precisa ter um `tool_result` com o mesmo `tool_use_id`.
- O `is_error` avisa o modelo de que a ferramenta falhou, para ele tentar outra coisa.
- O limite de 10 iterações evita laço infinito (e gasto) se o modelo insistir.
- Os nomes das ferramentas vão direto ao modelo. Mantenha-os curtos e descritivos, e escreva boas docstrings no servidor: é a docstring que ensina o modelo a usar a ferramenta.

### 7.3 Expor o servidor local por túnel (só para testar o 7.1)

```powershell
# opção A: cloudflared
cloudflared tunnel --url http://localhost:8000

# opção B: ngrok
ngrok http 8000
```

O comando imprime uma URL `https://...`. Use `https://<essa-url>/mcp` no connector. O `/health` também fica acessível por ela.

> Durante o túnel, **qualquer pessoa na internet** alcança o seu servidor. A única barreira é a chave Bearer, então use uma chave forte e feche o túnel quando terminar.

---

## 8. Usando com a API da OpenAI

Mesma divisão da seção 7.

```powershell
pip install openai
$env:OPENAI_API_KEY = "sk-..."
```

> Nomes de modelo mudam. Os exemplos usam `gpt-5` como placeholder: troque pelo modelo que a sua conta tem. A forma exata dos parâmetros pode variar com a versão do SDK; confira a documentação da OpenAI se houver divergência.

### 8.1 Servidor MCP remoto (a OpenAI conecta no seu servidor)

Na Responses API, a ferramenta do tipo `mcp` aponta para a sua URL. Também exige **URL pública com HTTPS**.

```python
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

resp = client.responses.create(
    model="gpt-5",
    input="Quanto é 17 + 25? Use a ferramenta.",
    tools=[{
        "type": "mcp",
        "server_label": "meu_mcp_rest",
        "server_url": "https://SEU-DOMINIO-PUBLICO/mcp",
        "authorization": os.environ["MCP_API_KEY"],   # só o token, sem "Bearer"
        "require_approval": "never",
    }],
)
print(resp.output_text)
```

- `require_approval`: `"never"` executa direto; deixando o padrão, a API devolve um pedido de aprovação que você precisa responder antes da ferramenta rodar. Use aprovação em ferramentas com efeito colateral.
- `allowed_tools` (lista de nomes) restringe quais ferramentas o modelo enxerga.
- `server_label` identifica o servidor nos itens de saída (`mcp_list_tools`, `mcp_call`).

### 8.2 Loop local (o seu script é o cliente MCP)

Salve como `agente_openai.py`. É a mesma estrutura da seção 7.2, adaptada ao formato de *function calling* da OpenAI:

```python
import asyncio
import json
import os

import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import AsyncOpenAI

load_dotenv()

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
CHAVE = os.environ["MCP_API_KEY"]
MODELO = "gpt-5"
PERGUNTA = "Quanto é 17 + 25? E quantas palavras tem 'o rato roeu a roupa'?"


async def main():
    llm = AsyncOpenAI()

    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {CHAVE}"})
    async with http, streamable_http_client(URL, http_client=http) as streams:
        async with ClientSession(*streams[:2]) as mcp:
            await mcp.initialize()

            # ferramentas do MCP -> formato da OpenAI
            lista = await mcp.list_tools()
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                }
                for t in lista.tools
            ]

            messages = [{"role": "user", "content": PERGUNTA}]

            for _ in range(10):  # limite de segurança
                resp = await llm.chat.completions.create(
                    model=MODELO, messages=messages, tools=tools
                )
                msg = resp.choices[0].message
                messages.append(msg)

                if not msg.tool_calls:
                    print(msg.content)
                    return

                for call in msg.tool_calls:
                    args = json.loads(call.function.arguments)
                    r = await mcp.call_tool(call.function.name, args)
                    texto = "".join(c.text for c in r.content if c.type == "text")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": texto,
                    })


asyncio.run(main())
```

Diferenças em relação à Anthropic:

- O esquema da ferramenta vai em `parameters` (Anthropic: `input_schema`).
- Os argumentos chegam como **string JSON**, então é preciso `json.loads`.
- O resultado volta como mensagem `role: "tool"` com o `tool_call_id` (uma por chamada).

---

## 9. Indo para produção

O servidor já tem o essencial (Bearer, comparação segura, `/health`, recusa de iniciar sem chave). Para algo realmente de produção, falta cuidar do que está ao redor:

**HTTPS é obrigatório.** O Bearer viaja em texto puro; sem TLS qualquer um no caminho lê a chave. Ponha um proxy reverso na frente (Caddy, nginx, Traefik) ou use uma plataforma que já termina TLS (Cloud Run, Fly.io, Railway, Render, etc.) e deixe o Uvicorn escutando só localmente ou na rede privada.

**Atrás de proxy**, habilite no `uvicorn.run` de `server_rest.py` as linhas já deixadas em comentário (`proxy_headers=True, forwarded_allow_ips="*"`). Restrinja `forwarded_allow_ips` ao IP do proxy sempre que souber qual é.

**Segredos.** Não commite `.env`. Em produção, injete `MCP_API_KEYS` pelo gerenciador de segredos da plataforma. Use chaves longas e aleatórias (32+ bytes), uma por cliente, e troque-as periodicamente.

**Rotação de chave sem downtime:** adicione a nova ao `MCP_API_KEYS` (`velha,nova`), reinicie, migre os clientes, remova a velha, reinicie de novo.

**Rate limit e firewall.** O servidor não limita requisições. Aplique limites no proxy/gateway, e se possível libere a porta só para os IPs que precisam (para o connector da Anthropic/OpenAI, consulte os IPs de saída que eles publicam).

**Logs e auditoria.** O Uvicorn já registra cada requisição. Para saber *qual cliente* chamou, associe cada chave a um nome e registre o nome no middleware. Também registre as chamadas de ferramenta (nome, argumentos, duração) dentro das ferramentas.

**Mais de uma instância.** Por padrão as sessões MCP ficam na memória do processo. Atrás de load balancer, ou se o processo reiniciar, um cliente com sessão aberta pode receber erro de sessão. Para escalar horizontalmente, defina `STATELESS=1` (o `criar_app()` passa `stateless_http=True` ao MCP e deixa de guardar sessões na memória).

**Validação de entrada e efeitos colaterais.** Tudo que a IA manda é entrada não confiável. Valide argumentos, limite tamanho/tempo, e para ferramentas perigosas (apagar, enviar, pagar) exija confirmação do usuário (aprovação no Claude Code, `require_approval` na OpenAI).

**Limitações do esquema atual de autenticação:**

| Limitação | Alternativa |
|---|---|
| Chave estática, sem expiração | OAuth 2.1 / tokens JWT de curta duração |
| Todas as chaves têm o mesmo poder | mapear chave → permissões dentro do middleware |
| Sem rate limit por chave | gateway de API (Kong, Cloudflare, etc.) |

**Exemplo de execução com mais de um worker** (testado com 2 workers e com `STATELESS=1`; sem ele, as sessões ficam na memória de cada worker e podem falhar entre workers):

```powershell
$env:STATELESS = "1"
.venv\Scripts\python -m uvicorn --factory server_rest:criar_app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 10. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Defina MCP_API_KEYS ...` e o servidor não sobe | variável vazia | preencha `MCP_API_KEYS` no `.env` ou no ambiente |
| `401 unauthorized` | chave ausente/errada, ou espaço sobrando | confira o header `Authorization: Bearer <chave>` e o `.env` |
| `400`/`406` no curl | faltou `Accept: application/json, text/event-stream` | adicione os dois tipos no header |
| `Connection refused` | servidor desligado ou porta diferente | suba o servidor; confira `PORT` e a URL |
| `KeyError: 'MCP_API_KEY'` no cliente | `.env` sem a variável (ou rodando fora da pasta) | defina `MCP_API_KEY`; rode da raiz do projeto |
| Claude Code mostra o servidor como `failed` | URL, porta ou chave erradas | `claude mcp get meu-mcp-rest`, corrija e `/mcp` para reconectar |
| Connector da Anthropic/OpenAI dá erro de conexão | URL não é pública ou não é HTTPS | use túnel ou deploy com HTTPS; `localhost` não funciona nesse modo |
| Erro de validação no connector da Anthropic | faltou `mcp_toolset` em `tools`, ou os nomes não coincidem | declare as duas peças com o mesmo nome |
| Erro de beta inválido | nome do header beta mudou | confira a documentação atual do MCP connector |
| Erro de sessão após reiniciar, ou só com várias instâncias | sessões ficam na memória do processo | reconecte; para escalar use `STATELESS=1` |
| Caracteres estranhos (`n�meros`) no terminal | codificação do console do Windows | só visual; rode `chcp 65001` ou `$env:PYTHONIOENCODING="utf-8"` |
| `ModuleNotFoundError: mcp.server.mcpserver` | SDK `mcp` antigo | `pip install -U mcp` (o projeto usa a série 2.x) |

---

## 11. Como adicionar novas ferramentas

Em `server_rest.py` (e, se quiser, também em `server.py`), acrescente uma função com `@mcp.tool()`:

```python
@mcp.tool()
def inverter_texto(texto: str) -> str:
    """Inverte os caracteres de um texto."""
    return texto[::-1]
```

Regras:

- A **docstring** é o que o modelo lê para decidir *quando* usar a ferramenta. Seja específico.
- Os **tipos** dos parâmetros viram o JSON Schema que o modelo recebe, então anote sempre (`int`, `str`, `list[str]`, `bool`...).
- Retorne tipos simples (`str`, números, listas, dicts).
- Reinicie o servidor depois de editar. Os clientes pegam a lista nova ao reconectar (no Claude Code, `/mcp`).
- Para ferramentas com efeito colateral, valide a entrada e, se fizer sentido, exija confirmação do usuário no cliente.
