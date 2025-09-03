# chat.py
import asyncio, json, os
from typing import Any
from dataclasses import dataclass
from mcp import ClientSession, types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp_logger import MCPLogger
from dotenv import load_dotenv

load_dotenv()

try:
    import anthropic
except Exception:
    anthropic = None

@dataclass
class ServerConn:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]

class MCPHost:
    """
    - Conecta N servidores definidos en servers.config.json
    - Descubre tools y las expone al LLM como `server.tool` (namespacing)
    - Loggea: connect, list_tools, call_tool.request, call_tool.response
    """
    def __init__(self, config_path="servers.config.json"):
        self.logger = MCPLogger()
        cfg = json.load(open(config_path, "r", encoding="utf-8"))
        self.server_defs = [ServerConn(s["name"], s["command"], s["args"], s.get("env", {})) for s in cfg["servers"]]
        self.sessions: dict[str, ClientSession] = {}
        self._connections = {}
        self.tools_schema: list[dict[str, Any]] = []  # para el LLM
        self.tool_name_map: dict[str, tuple[str, str]] = {}

    async def connect_all(self):
        for s in self.server_defs:
            params = StdioServerParameters(command=s.command, args=s.args, env=s.env)
            client = stdio_client(params)
            read, write = await client.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            self.sessions[s.name] = session
            self._connections[s.name] = client
            self.logger.write("connect", {"server": s.name, "command": s.command, "args": s.args})

        # Descubrir tools y preparar definiciones para tool-calling (Anthropic)
        await self._discover_all_tools()

    async def _discover_all_tools(self):
        self.tools_schema.clear()
        self.tool_name_map.clear()  # <— asegúrate de limpiar el mapa
        for server, session in self.sessions.items():
            tools = await session.list_tools()
            self.logger.write("list_tools", {"server": server, "tools": [t.name for t in tools.tools]})
            for t in tools.tools:
                # Nombre seguro para Anthropic (sin '.')
                safe_name = f"{server}__{t.name}"
                self.tool_name_map[safe_name] = (server, t.name)
                self.tools_schema.append({
                    "name": safe_name,
                    "description": f"[{server}] {t.description or ''}",
                    "input_schema": t.inputSchema or {"type": "object", "properties": {}}
                })

    async def call_tool(self, namespaced: str, arguments: dict[str, Any]):
        """Despacha safe_name → (server, tool). Loggea request/response."""
        if namespaced not in self.tool_name_map:
            raise ValueError(f"Herramienta '{namespaced}' no registrada. Disponibles: {list(self.tool_name_map.keys())}")
        server, tool = self.tool_name_map[namespaced]
        session = self.sessions[server]
        self.logger.write("call_tool.request", {"server": server, "tool": tool, "args": arguments})
        result = await session.call_tool(tool, arguments=arguments)
        text_blocks = [c.text for c in result.content if isinstance(c, types.TextContent)]
        payload = {
            "server": server,
            "tool": tool,
            "structured": getattr(result, "structuredContent", None),
            "text": "\n".join(text_blocks)
        }
        self.logger.write("call_tool.response", payload)
        return payload


    async def disconnect_all(self):
        for name, session in list(self.sessions.items()):
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                pass
        for name, conn in list(self._connections.items()):
            try:
                await conn.__aexit__(None, None, None)
            except Exception:
                pass

class ChatApp:
    """
    Mantiene contexto y hace tool-calling con Anthropic:
    - 1ª vuelta: el LLM decide si usar herramientas (tool_use)
    - Ejecutamos cada tool y devolvemos tool_result
    - 2ª vuelta: el LLM redacta respuesta natural final
    """
    def __init__(self, host: MCPHost):
        self.host = host
        self.messages: list[dict[str, Any]] = []  # historial Anthropic (enriquecido)
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
            tools=self.host.tools_schema,  # <-- definiciones de tools con namespace
            messages=self.messages,
            max_tokens=600
        )

        # Guardar assistant (puede traer texto + tool_use)
        self.messages.append({"role": "assistant", "content": resp.content})

        # ¿Pidió herramienta(s)?
        tool_uses = [c for c in resp.content if getattr(c, "type", "") == "tool_use"]
        if tool_uses:
            tool_results = []
            for tu in tool_uses:
                name = tu.name             # namespaced: server.tool
                args = tu.input or {}
                self.logger.write("llm.tool_use", {"name": name, "args": args})
                # Ejecutar herramienta en MCP
                result = await self.host.call_tool(name, args)
                # Devolvemos tool_result al LLM
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
            # 2) Segunda vuelta: enviar tool_result como mensaje del rol user
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
            return final_text

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