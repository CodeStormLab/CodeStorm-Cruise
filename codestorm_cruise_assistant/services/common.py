"""Tipi e funzioni condivisi tra il loop agentico e gli adattatori dei provider."""


class AgentError(Exception):
    pass


class ToolSpec:
    """Tool MCP già tradotto in un nome valido per tutti i provider."""

    def __init__(self, name, description, schema):
        self.name = name
        self.description = description
        self.schema = schema


class ToolCall:
    def __init__(self, id, name, args):
        self.id = id
        self.name = name
        self.args = args


class Step:
    """Risultato di una chiamata al modello.

    ``stop``: 'tool' (ci sono tool da eseguire), 'end', 'refusal', 'max_tokens'.
    """

    def __init__(self, text='', calls=None, stop='end', detail=''):
        self.text = text
        self.calls = calls or []
        self.stop = stop
        self.detail = detail


def key_hint(api_key, prefixes=()):
    """Prime 3 cifre dopo il prefisso fisso del provider e ultime 3 della key,
    per capire quale key è in uso."""
    prefix = next((p for p in prefixes if api_key.startswith(p)), '')
    body = api_key[len(prefix):]
    return f"(key: {prefix}{body[:3]}…{api_key[-3:]})"
