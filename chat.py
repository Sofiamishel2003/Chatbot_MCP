# chat.py
import asyncio, json, os
from contextlib import AsyncExitStack
from typing import Any, Optional
from types import SimpleNamespace
import httpx
from dataclasses import dataclass, field

from mcp import ClientSession, types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp_logger import MCPLogger
from dotenv import load_dotenv

# HTTP client para streamable-http (con fallback por compatibilidad)
try:
    from mcp.client.streamable_http import streamablehttp_client
except Exception:
    streamablehttp_client = None

load_dotenv()

try:
    import anthropic
except Exception:
    anthropic = None

@dataclass
class ServerConn:
    name: str
    # stdio
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # http
    transport: str = "stdio"                      # "stdio" | "streamable-http" | "http"
    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
class ShimHTTPSession:
    """
    Cliente HTTP simple para el shim stateless (/mcp).
    Expone los mismos métodos que usamos del ClientSession: list_tools() y call_tool().
    """
    def __init__(self, url: str, headers: dict | None = None):
        self.url = url.rstrip("/")
        base = {"Content-Type": "application/json", "Accept": "application/json"}
        self.headers = {**base, **(headers or {})}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_tools(self):
        assert self._client is not None
        payload = {"jsonrpc": "2.0", "id": "list", "method": "tools/list", "params": {}}
        r = await self._client.post(self.url, headers=self.headers, json=payload)
        r.raise_for_status()
        data = r.json()
        tools = []
        for t in data.get("result", {}).get("tools", []):
            tools.append(SimpleNamespace(
                name=t.get("name", ""),
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {"type": "object", "properties": {}})
            ))
        return SimpleNamespace(tools=tools)

    async def call_tool(self, tool_name: str, arguments: dict):
        assert self._client is not None
        payload = {
            "jsonrpc": "2.0",
            "id": "call",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        r = await self._client.post(self.url, headers=self.headers, json=payload)
        r.raise_for_status()
        data = r.json()
        # El shim devuelve 'result' como lista de bloques [{type:"text", text:"..."}]
        content_blocks = []
        for c in (data.get("result") or []):
            text = c.get("text", "") if isinstance(c, dict) else str(c)
            content_blocks.append(SimpleNamespace(text=text))
        return SimpleNamespace(content=content_blocks, structuredContent=None)

class MCPHost:
    """
    - Conecta N servidores definidos en servers.config.json
    - Descubre tools y las expone al LLM como `server.tool` (namespacing)
    - Loggea: connect, list_tools, call_tool.request, call_tool.response
    """
    def __init__(self, config_path="servers.config.json"):
        self.logger = MCPLogger()
        cfg = json.load(open(config_path, "r", encoding="utf-8"))
        # ExitStack para administrar TODOS los contextos (clientes + sesiones)
        self._stack: AsyncExitStack | None = None
        # admite stdio y streamable-http; guarda campos flexibles en ServerConn
        self.server_defs = []
        for s in cfg["servers"]:
            self.server_defs.append(
                ServerConn(
                    name=s["name"],
                    command=s.get("command", ""),
                    args=s.get("args", []),
                    env=s.get("env", {}),
                    transport=s.get("transport", "stdio"),
                    url=s.get("url"),
                    headers=s.get("headers", {}),
                )
            )

        self.sessions: dict[str, ClientSession] = {}
        self._connections = {}
        self.tools_schema: list[dict[str, Any]] = []  # para el LLM
        self.input_schema_map: dict[str, dict[str, Any]] = {} 
        self.tool_name_map: dict[str, tuple[str, str]] = {}

    async def connect_all(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        for s in self.server_defs:
            # Seleccionar cliente según transporte
            if s.transport == "stdio":
                params = StdioServerParameters(command=s.command, args=s.args, env=s.env)
                client_cmgr = stdio_client(params)
                streams = await self._stack.enter_async_context(client_cmgr)
                read, write, *rest = streams
                session_cmgr = ClientSession(read, write)
                session = await self._stack.enter_async_context(session_cmgr)

            elif s.transport in ("streamable-http", "http"):
                # Si quisieras seguir usando el endpoint MCP real con sesiones
                # (NO recomendado ahora mismo porque tu server remoto da 500 en /mcp-stream)
                if streamablehttp_client is None:
                    raise RuntimeError("Tu versión de 'mcp' no trae streamablehttp_client. pip install -U mcp")
                if not s.url:
                    raise ValueError(f"Server {s.name} missing 'url' for streamable-http")
                client_cmgr = streamablehttp_client(url=s.url, headers=s.headers)
                streams = await self._stack.enter_async_context(client_cmgr)
                read, write, *rest = streams
                session_cmgr = ClientSession(read, write)
                session = await self._stack.enter_async_context(session_cmgr)

            elif s.transport == "shim":
                if not s.url:
                    raise ValueError(f"Server {s.name} missing 'url' for shim")
                session = await self._stack.enter_async_context(ShimHTTPSession(s.url, s.headers))
                # Nota: para shim no hay ClientSession, guardamos el propio 'session'

            else:
                raise ValueError(f"Unknown transport for server {s.name}: {s.transport}")

            # Inicializa solo si es ClientSession (no para shim)
            if hasattr(session, "initialize"):
                await session.initialize()

            self.sessions[s.name] = session
            self._connections[s.name] = session  # referencia útil
            self.logger.write("connect", {"server": s.name, "transport": s.transport})

        # Descubrir tools y preparar definiciones para tool-calling (Anthropic)
        await self._discover_all_tools()

    async def _discover_all_tools(self):
        self.tools_schema.clear()
        self.tool_name_map.clear()
        self.input_schema_map.clear()
        for server, session in self.sessions.items():
            tools = await session.list_tools()
            self.logger.write("list_tools", {"server": server, "tools": [t.name for t in tools.tools]})
            for t in tools.tools:
                # Nombre seguro para Anthropic (sin '.')
                safe_name = f"{server}__{t.name}"
                schema = t.inputSchema or {"type": "object", "properties": {}}                
                self.input_schema_map[safe_name] = schema
                self.tool_name_map[safe_name] = (server, t.name)
                self.tools_schema.append({
                    "name": safe_name,
                    "description": f"[{server}] {t.description or ''}",
                    "input_schema": schema
                })

    async def call_tool(self, namespaced: str, arguments: dict[str, Any]):
        if namespaced not in self.tool_name_map:
            raise ValueError(f"Herramienta '{namespaced}' no registrada. Disponibles: {list(self.tool_name_map.keys())}")
        server, tool = self.tool_name_map[namespaced]
        session = self.sessions[server]
        # --- Auto-wrap si el schema espera 'params' ---
        schema = self.input_schema_map.get(namespaced) or {}
        props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
        tool_args = arguments
        if "params" in props and "params" not in arguments:
            tool_args = {"params": arguments}

        self.logger.write("call_tool.request", {"server": server, "tool": tool, "args": tool_args})
        result = await session.call_tool(tool, arguments=tool_args)
        text_blocks = []
        for c in getattr(result, "content", []) or []:
            # Soporta tanto mcp.Types.TextContent como SimpleNamespace(text=...)
            if hasattr(c, "text"):
                text_blocks.append(c.text)

        payload = {
            "server": server,
            "tool": tool,
            "structured": getattr(result, "structuredContent", None),
            "text": "\n".join(text_blocks)
        }
        self.logger.write("call_tool.response", payload)
        return payload


    async def disconnect_all(self):
        if self._stack:
            try:
                await self._stack.aclose()
            finally:
                self._stack = None
        self.sessions.clear()
        self._connections.clear()

class ChatApp:
    """
    Mantiene contexto y hace tool-calling con Anthropic:
    - 1ª vuelta: el LLM decide si usar herramientas (tool_use)
    - Ejecutamos cada tool y devolvemos tool_result
    - 2ª vuelta: el LLM redacta respuesta natural final
    """
    def __init__(self, host: MCPHost):
        self.host = host
        self.messages: list[dict[str, Any]] = []  # historial Anthropic
        self.logger = host.logger
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if anthropic and os.getenv("ANTHROPIC_API_KEY") else None
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
        self.system = (
            "Eres un asistente en español. Responde en lenguaje natural.\n"
            "Cuando la consulta trate de PELÍCULAS u otras funciones disponibles, usa las herramientas MCP expuestas.\n"
            "Usa únicamente los parámetros listados en el schema de la herramienta.\n"
        )

    def _msg_user_text(self, text: str) -> dict:
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    async def ask(self, user_text: str) -> str:
        self.messages.append(self._msg_user_text(user_text))

        if not self.client:
            offline = f"(offline) Recibido: {user_text}"
            self.messages.append({"role": "assistant", "content": [{"type": "text", "text": offline}]})
            return offline

        # 1) Llamada con herramientas
        resp = self.client.messages.create(
            model=self.model,
            system=self.system,
            tools=self.host.tools_schema, # herramientas disponibles
            messages=self.messages,
            max_tokens=600
        )

        # Guardar assistant (puede traer texto + tool_use)
        self.messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [c for c in resp.content if getattr(c, "type", "") == "tool_use"]
        if tool_uses:
            tool_results = []
            confirmations = []  # guardar confirmaciones para afirmar en el mensaje final
            for tu in tool_uses:
                name = tu.name
                args = tu.input or {}
                self.logger.write("llm.tool_use", {"name": name, "args": args})
                # Ejecutar herramienta en MCP
                result = await self.host.call_tool(name, args)
                # Confirmación legible
                confirm = [
                    f"**✅ Tool executed**",
                    f"- server: `{result['server']}`",
                    f"- tool: `{result['tool']}`",
                ]

                confirmations.append("\n".join(confirm))

                # Devolvemos tool_result al LLM
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
            # 2) Segunda vuelta: enviar tool_result
            self.messages.append({"role": "user", "content": tool_results})
            resp2 = self.client.messages.create(
                model=self.model,
                system=self.system,
                messages=self.messages,
                max_tokens=800
            )
            final_text = "".join([c.text for c in resp2.content if getattr(c, "type", "") == "text"])
            self.messages.append({"role": "assistant", "content": resp2.content})
            self.logger.write("llm.final_response", {"text": final_text})
            # DEVUELVE confirmaciones + respuesta del LLM
            return "\n\n".join(confirmations + [final_text])
        # Si no usó herramientas, devolver texto directo
        direct_text = "".join([c.text for c in resp.content if getattr(c, "type", "") == "text"])
        self.logger.write("llm.direct_response", {"text": direct_text})
        return direct_text

HELP = """
Comandos:
/servers         → lista servidores conectados
/tools <server>  → lista herramientas de un servidor
/logpath         → muestra ruta del log JSONL
/history         → cuenta mensajes de la sesión
/clear           → limpia el contexto de la sesión
/help
"""

async def main():
    host = MCPHost("servers.config.json")
    await host.connect_all()
    app = ChatApp(host)
    print("Chatbot MCP listo. Escribe en lenguaje natural. Usa /help para ayuda.")
    try:
        while True:
            user = input("> ").strip()
            if not user:
                continue
            if user == "/help": print(HELP); continue
            if user == "/servers": print("Conectados:", ", ".join(host.sessions.keys())); continue
            if user.startswith("/tools "):
                srv = user.split(maxsplit=1)[1]
                tools = await host.sessions[srv].list_tools()
                for t in tools.tools: print("-", t.name, ":", t.description or "")
                continue
            if user == "/logpath": print("logs/mcp_log.jsonl"); continue
            if user == "/history": print(f"Mensajes en sesión: {len(app.messages)}"); continue
            if user == "/clear": app.messages.clear(); print("Contexto limpiado."); continue
            # Conversación natural
            reply = await app.ask(user)
            print(reply)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        await host.disconnect_all()

if __name__ == "__main__":
    asyncio.run(main())