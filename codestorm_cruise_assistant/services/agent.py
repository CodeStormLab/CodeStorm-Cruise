"""Loop agentico: Claude (Anthropic API) + tool del server MCP di Odoo.

Il processo Odoo fa da client MCP: legge i tool da /mcp, li passa a Claude
come tool "client", esegue le chiamate richieste dal modello e gli rimanda i
risultati finché il modello non termina il turno.
"""
import json
import logging
import re

from .mcp_client import McpClient, McpError

_logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20
MAX_TOOL_RESULT_CHARS = 100_000
# Modelli che accettano il fallback server-side sui rifiuti (fallbacks="default").
FALLBACK_MODELS = {
    'claude-opus-5-5', 'claude-opus-5', 'claude-sonnet-5-5',
    'claude-fable-5-1', 'claude-fable-5-2',
}
FALLBACK_BETA = 'server-side-fallback-2026-07-01'


class AgentError(Exception):
    pass


class AgentResult:
    def __init__(self):
        self.history = []        # trascrizione API aggiornata
        self.events = []         # messaggi da mostrare: dict(role, content, tool_name, is_error)


def _tool_name(name, used):
    clean = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:64] or 'tool'
    base, i = clean, 1
    while clean in used:
        suffix = f'_{i}'
        clean = base[:64 - len(suffix)] + suffix
        i += 1
    return clean


def _mcp_tools_to_claude(mcp_tools):
    tools, name_map = [], {}
    for t in mcp_tools:
        name = _tool_name(t['name'], name_map)
        name_map[name] = t['name']
        schema = t.get('inputSchema') or {'type': 'object', 'properties': {}}
        schema.setdefault('type', 'object')
        tools.append({
            'name': name,
            'description': (t.get('description') or t.get('title') or t['name'])[:10000],
            'input_schema': schema,
        })
    return tools, name_map


def _mcp_result_to_blocks(result):
    """Converte il risultato MCP (content[]) in blocchi tool_result Claude."""
    blocks = []
    for item in result.get('content') or []:
        kind = item.get('type')
        if kind == 'text':
            blocks.append({'type': 'text', 'text': item.get('text', '')})
        elif kind == 'image' and item.get('data'):
            blocks.append({'type': 'image', 'source': {
                'type': 'base64',
                'media_type': item.get('mimeType', 'image/png'),
                'data': item['data'],
            }})
        else:
            blocks.append({'type': 'text', 'text': json.dumps(item, ensure_ascii=False, default=str)})
    if not blocks and result.get('structuredContent') is not None:
        blocks.append({'type': 'text', 'text': json.dumps(
            result['structuredContent'], ensure_ascii=False, default=str)})
    if not blocks:
        blocks.append({'type': 'text', 'text': '(nessun risultato)'})
    for b in blocks:
        if b['type'] == 'text' and len(b['text']) > MAX_TOOL_RESULT_CHARS:
            b['text'] = b['text'][:MAX_TOOL_RESULT_CHARS] + '\n…[risultato troncato]'
    return blocks


def _preview(blocks, limit=400):
    text = ' '.join(b.get('text', '[immagine]') for b in blocks)
    return text if len(text) <= limit else text[:limit] + '…'


def run_turn(config, history, user_text):
    """Esegue un turno completo. ``history`` è la trascrizione API precedente.

    ``config``: dict con anthropic_api_key, model, effort, system_prompt,
    mcp_url, mcp_api_key.
    """
    try:
        import anthropic
    except ImportError as e:
        raise AgentError("Il pacchetto Python 'anthropic' non è installato "
                         "nel container Odoo.") from e

    result = AgentResult()
    messages = list(history) + [{'role': 'user', 'content': user_text}]

    # --- MCP: handshake e tool disponibili -------------------------------
    try:
        mcp = McpClient(config['mcp_url'], config['mcp_api_key'])
        mcp.initialize()
        tools, name_map = _mcp_tools_to_claude(mcp.list_tools())
    except McpError as e:
        raise AgentError(str(e)) from e

    client_kwargs = {}
    if config.get('anthropic_api_key'):
        client_kwargs['api_key'] = config['anthropic_api_key']
    try:
        client = anthropic.Anthropic(**client_kwargs)
    except anthropic.AnthropicError as e:
        raise AgentError("API key Anthropic non configurata (Impostazioni > "
                         "Cruise Assistant).") from e

    model = config['model']
    request = {
        'model': model,
        'max_tokens': 16000,
        'system': config['system_prompt'],
        'messages': messages,
        'thinking': {'type': 'adaptive'},
        'output_config': {'effort': config['effort']},
        'cache_control': {'type': 'ephemeral'},
    }
    if tools:
        request['tools'] = tools
    if model in FALLBACK_MODELS:
        request['betas'] = [FALLBACK_BETA]
        request['fallbacks'] = 'default'

    for _ in range(MAX_ITERATIONS):
        try:
            response = client.beta.messages.create(**request)
        except anthropic.AuthenticationError as e:
            raise AgentError("API key Anthropic non valida.") from e
        except anthropic.RateLimitError as e:
            raise AgentError("Limite di richieste Anthropic raggiunto, riprova tra poco.") from e
        except anthropic.BadRequestError as e:
            raise AgentError(f"Richiesta non valida: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise AgentError(f"Errore API Anthropic ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AgentError("Impossibile contattare l'API Anthropic.") from e

        # Il contenuto va rimandato invariato (thinking, fallback, tool_use...).
        messages.append({'role': 'assistant', 'content': [b.to_dict() for b in response.content]})

        text = '\n\n'.join(b.text for b in response.content if b.type == 'text').strip()
        if text:
            result.events.append({'role': 'assistant', 'content': text})

        if response.stop_reason == 'refusal':
            result.events.append({
                'role': 'assistant', 'is_error': True,
                'content': "Il modello ha rifiutato di rispondere a questa richiesta.",
            })
            break
        if response.stop_reason == 'max_tokens':
            result.events.append({
                'role': 'assistant', 'is_error': True,
                'content': "Risposta interrotta: raggiunto il limite di token.",
            })
            break
        if response.stop_reason != 'tool_use':
            break

        tool_results = []
        for block in response.content:
            if block.type != 'tool_use':
                continue
            mcp_name = name_map.get(block.name, block.name)
            args = block.input if isinstance(block.input, dict) else {}
            try:
                mcp_result = mcp.call_tool(mcp_name, args)
                blocks = _mcp_result_to_blocks(mcp_result)
                is_error = bool(mcp_result.get('isError'))
            except McpError as e:
                blocks = [{'type': 'text', 'text': f'Errore MCP: {e}'}]
                is_error = True
            _logger.info("Cruise assistant: tool %s -> %s", mcp_name,
                         'errore' if is_error else 'ok')
            tool_results.append({
                'type': 'tool_result', 'tool_use_id': block.id,
                'content': blocks, 'is_error': is_error,
            })
            result.events.append({
                'role': 'tool', 'tool_name': mcp_name, 'is_error': is_error,
                'content': json.dumps(args, ensure_ascii=False, default=str)
                           + '\n→ ' + _preview(blocks),
            })
        # Tutti i tool_result in un unico messaggio utente.
        messages.append({'role': 'user', 'content': tool_results})
    else:
        result.events.append({
            'role': 'assistant', 'is_error': True,
            'content': "Interrotto: troppe chiamate ai tool in un solo turno.",
        })
        # Chiude il turno in modo coerente: l'ultimo messaggio è un tool_result,
        # serve una risposta assistant prima del prossimo messaggio utente.
        messages.append({'role': 'assistant', 'content': [{
            'type': 'text', 'text': '(turno interrotto per troppe chiamate ai tool)'}]})

    result.history = messages
    return result
