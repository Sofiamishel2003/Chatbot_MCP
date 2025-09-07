# app_streamlit.py
import os
import io
import json
import time
import queue
import asyncio
import threading
from pathlib import Path
from typing import Any, Awaitable  

import streamlit as st
from chat import MCPHost, ChatApp

LOG_PATH = Path("logs/mcp_log.jsonl") 

# -----------------------------
# Utilidad: event loop en hilo
# -----------------------------
class AsyncRunner:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro: Awaitable[Any]):
        """Ejecuta una corrutina en el loop de fondo y espera el resultado."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    def stop(self):
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

# -----------------------------
# Estado de la app
# -----------------------------
def init_state():
    if "runner" not in st.session_state:
        st.session_state.runner = AsyncRunner()
    if "config_path" not in st.session_state:
        st.session_state.config_path = "servers.config.json"
    if "host" not in st.session_state:
        st.session_state.host = None
    if "app" not in st.session_state:
        st.session_state.app = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []  # [{"role":"user"/"assistant","text":str}]

def connect_host():
    # Cierra conexiones previas si las hay
    if st.session_state.host:
        try:
            st.session_state.runner.run(st.session_state.host.disconnect_all())
        except Exception:
            pass

    host = MCPHost(st.session_state.config_path)
    st.session_state.runner.run(host.connect_all())
    app = ChatApp(host)

    st.session_state.host = host
    st.session_state.app = app

def disconnect_host():
    if st.session_state.host:
        try:
            st.session_state.runner.run(st.session_state.host.disconnect_all())
        except Exception:
            pass
    st.session_state.host = None
    st.session_state.app = None

# -----------------------------
# Utilidades varias
# -----------------------------
def tail_jsonl(path: Path, max_lines: int = 100) -> list[str]:
    if not path.exists():
        return []
    # Lectura simple (archivo pequeño); si crece mucho, se puede optimizar
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-max_lines:]

def render_sidebar():
    st.sidebar.header("MCP Host")
    st.sidebar.text_input("Config file", key="config_path")
    colA, colB = st.sidebar.columns(2)
    with colA:
        if st.button("Connect / Reconnect", type="primary", use_container_width=True):
            try:
                connect_host()
                st.success("Connected ✅")
            except Exception as e:
                st.error(f"Connect error: {e}")
    with colB:
        if st.button("Disconnect", use_container_width=True):
            try:
                disconnect_host()
                st.info("Disconnected")
            except Exception as e:
                st.error(f"Disconnect error: {e}")

    host = st.session_state.host
    if host:
        st.sidebar.subheader("Servers")
        if host.sessions:
            for name in host.sessions.keys():
                with st.sidebar.expander(f"{name}", expanded=False):
                    try:
                        tools = st.session_state.runner.run(host.sessions[name].list_tools())
                        if hasattr(tools, "tools"):
                            for t in tools.tools:
                                st.caption(f"- {t.name}")
                        else:
                            st.caption("(no tools)")
                    except Exception as e:
                        st.caption(f"(error listing tools: {e})")
        else:
            st.sidebar.write("No sessions")
    else:
        st.sidebar.write("Not connected")

    st.sidebar.subheader("Logs")
    if st.sidebar.toggle("Show last 100 log lines", value=False):
        for ln in tail_jsonl(LOG_PATH, 100):
            st.sidebar.code(ln, language="json")

def render_chat_message(role: str, text: str):
    with st.chat_message(role):
        st.markdown(text)

def handle_command(cmd: str) -> str:
    """Comandos estilo consola: /servers, /tools <server>, /clear."""
    host = st.session_state.host
    if cmd.strip() == "/servers":
        if not host:
            return "Host not connected."
        names = ", ".join(host.sessions.keys())
        return f"Connected servers: {names or '(none)'}"

    if cmd.strip().startswith("/tools "):
        if not host:
            return "Host not connected."
        srv = cmd.strip().split(maxsplit=1)[1]
        if srv not in host.sessions:
            return f"Unknown server '{srv}'. Use /servers to list."
        try:
            tools = st.session_state.runner.run(host.sessions[srv].list_tools())
            if hasattr(tools, "tools"):
                items = "\n".join([f"- {t.name}: {getattr(t,'description','') or ''}" for t in tools.tools])
                return f"Tools in **{srv}**:\n{items or '(none)'}"
        except Exception as e:
            return f"Error listing tools: {e}"

    if cmd.strip() == "/clear":
        st.session_state.chat_history.clear()
        # También limpias el contexto del ChatApp (historial Anthropic)
        if st.session_state.app:
            st.session_state.app.messages.clear()
        return "Conversation cleared."

    if cmd.strip() == "/help":
        return (
            "**Commands:**\n"
            "- `/servers` — list connected servers\n"
            "- `/tools <server>` — list tools of a server\n"
            "- `/clear` — clear conversation\n"
            "- `/help` — show this help"
        )

    return "Unknown command. Try `/help`."

# -----------------------------
# Streamlit app
# -----------------------------
st.set_page_config(page_title="MCP Chat UI", page_icon="💬", layout="wide")
init_state()
render_sidebar()

st.title("💬 MCP Chat UI Bellaco")
st.caption("Ask in natural language. The app will use your MCP tools when needed.")

# Conéctate al cargar si aún no hay host
if st.session_state.host is None:
    try:
        connect_host()
        st.success("Connected ✅")
    except Exception as e:
        st.error(f"Connect error: {e}")

# Render del historial
for msg in st.session_state.chat_history:
    render_chat_message(msg["role"], msg["text"])

# Input del chat
user_text = st.chat_input("Type your message...")
if user_text:
    # Muestra al usuario
    st.session_state.chat_history.append({"role": "user", "text": user_text})
    render_chat_message("user", user_text)

    # Comandos tipo consola
    if user_text.strip().startswith("/"):
        reply = handle_command(user_text)
        st.session_state.chat_history.append({"role": "assistant", "text": reply})
        render_chat_message("assistant", reply)
        st.stop()

    # Pregunta al ChatApp (con tools)
    app = st.session_state.app
    host = st.session_state.host
    if app and host:
        try:
            reply = st.session_state.runner.run(app.ask(user_text))
        except Exception as e:
            reply = f"⚠️ Error while answering: `{e}`"
    else:
        reply = "Host not connected."

    st.session_state.chat_history.append({"role": "assistant", "text": reply})
    render_chat_message("assistant", reply)
