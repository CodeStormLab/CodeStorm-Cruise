"""Loop agentico: LLM configurabile + tool del server MCP di Odoo.

Il processo Odoo fa da client MCP: legge i tool da /mcp, li passa al modello
scelto nelle impostazioni (Claude, Gemini, Groq o Mistral), esegue
le chiamate richieste e gli rimanda i risultati finché il modello non termina
il turno. Le differenze tra provider stanno negli adattatori in ``providers/``.
"""
import json
import logging
import os
import re

from .common import AgentError, ToolSpec
from .mcp_client import McpClient, McpError
from .providers import PROVIDERS, create_session

_logger = logging.getLogger(__name__)

__all__ = ['AgentError', 'run_turn']

MAX_ITERATIONS = 20
MAX_TOOL_RESULT_CHARS = 100_000


class AgentResult:
    def __init__(self):
        self.history = []        # trascrizione API aggiornata (formato del provider)
        self.events = []         # messaggi da mostrare: dict(role, content, tool_name, is_error)


def _tool_name(name, used):
    # Nome valido per tutti i provider: lettere, cifre, _ e -, max 64
    # caratteri, primo carattere lettera o underscore.
    clean = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:64] or 'tool'
    if not re.match(r'[a-zA-Z_]', clean):
        clean = ('_' + clean)[:64]
    base, i = clean, 1
    while clean in used:
        suffix = f'_{i}'
        clean = base[:64 - len(suffix)] + suffix
        i += 1
    return clean


def _mcp_tools(mcp_tools):
    tools, name_map = [], {}
    for t in mcp_tools:
        name = _tool_name(t['name'], name_map)
        name_map[name] = t['name']
        schema = dict(t.get('inputSchema') or {'type': 'object', 'properties': {}})
        schema.pop('$schema', None)
        schema.setdefault('type', 'object')
        schema.setdefault('properties', {})
        tools.append(ToolSpec(
            name, (t.get('description') or t.get('title') or t['name'])[:10000], schema))
    return tools, name_map


def _mcp_result_to_text(result):
    """Converte il risultato MCP (content[]) in testo."""
    parts = []
    for item in result.get('content') or []:
        kind = item.get('type')
        if kind == 'text':
            parts.append(item.get('text', ''))
        elif kind == 'image':
            parts.append('[immagine]')
        else:
            parts.append(json.dumps(item, ensure_ascii=False, default=str))
    if not parts and result.get('structuredContent') is not None:
        parts.append(json.dumps(result['structuredContent'], ensure_ascii=False, default=str))
    text = '\n'.join(parts) or '(nessun risultato)'
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + '\n…[risultato troncato]'
    return text


def _preview(text, limit=400):
    return text if len(text) <= limit else text[:limit] + '…'


def run_turn(config, history, user_text):
    """Esegue un turno completo. ``history`` è la trascrizione API precedente,
    nel formato del provider in uso.

    ``config``: dict con provider, model, effort, system_prompt, mcp_url,
    mcp_api_key. Le API key sono lette solo dalle variabili d'ambiente
    (file .env del progetto), una per provider.
    """
    provider = config['provider']
    info = PROVIDERS.get(provider)
    if not info:
        raise AgentError(f"Provider LLM sconosciuto: {provider}")

    result = AgentResult()

    # --- MCP: handshake e tool disponibili -------------------------------
    try:
        mcp = McpClient(config['mcp_url'], config['mcp_api_key'])
        mcp.initialize()
        tools, name_map = _mcp_tools(mcp.list_tools())
    except McpError as e:
        raise AgentError(str(e)) from e

    api_key = os.environ.get(info['env'], '').strip()
    if not api_key:
        raise AgentError(f"API key {info['label']} non configurata: imposta "
                         f"{info['env']} nel file .env e ricrea il container.")

    session = create_session(provider, config, api_key, tools, history, user_text)

    for _ in range(MAX_ITERATIONS):
        step = session.step()
        if step.text:
            result.events.append({'role': 'assistant', 'content': step.text})

        if step.stop == 'refusal':
            result.events.append({
                'role': 'assistant', 'is_error': True,
                'content': "Il modello ha rifiutato di rispondere a questa richiesta"
                           + (f" ({step.detail})." if step.detail else "."),
            })
            break
        if step.stop == 'max_tokens':
            result.events.append({
                'role': 'assistant', 'is_error': True,
                'content': "Risposta interrotta: raggiunto il limite di token.",
            })
            break
        if step.stop != 'tool':
            break

        results = []
        for call in step.calls:
            mcp_name = name_map.get(call.name, call.name)
            try:
                mcp_result = mcp.call_tool(mcp_name, call.args)
                output = _mcp_result_to_text(mcp_result)
                is_error = bool(mcp_result.get('isError'))
            except McpError as e:
                output = f'Errore MCP: {e}'
                is_error = True
            _logger.info("Cruise assistant: tool %s -> %s", mcp_name,
                         'errore' if is_error else 'ok')
            results.append((call, output, is_error))
            result.events.append({
                'role': 'tool', 'tool_name': mcp_name, 'is_error': is_error,
                'content': json.dumps(call.args, ensure_ascii=False, default=str)
                           + '\n→ ' + _preview(output),
            })
        session.add_results(results)
    else:
        result.events.append({
            'role': 'assistant', 'is_error': True,
            'content': "Interrotto: troppe chiamate ai tool in un solo turno.",
        })
        # Chiude il turno in modo coerente: l'ultimo messaggio è un risultato
        # di tool, serve una risposta del modello prima del prossimo messaggio.
        session.close_interrupted('(turno interrotto per troppe chiamate ai tool)')

    result.history = session.history()
    return result
