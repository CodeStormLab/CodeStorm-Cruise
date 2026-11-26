"""Adattatore Anthropic Claude (SDK ``anthropic``)."""
import os

from ..common import AgentError, Step, ToolCall, key_hint
from . import PROVIDERS

MAX_TOKENS = 16000
# Modelli che accettano il fallback server-side sui rifiuti (fallbacks="default").
FALLBACK_MODELS = {
    'claude-opus-5-5', 'claude-opus-5', 'claude-sonnet-5-5',
    'claude-fable-5-1', 'claude-fable-5-2',
}
FALLBACK_BETA = 'server-side-fallback-2026-07-01'


class AnthropicSession:
    def __init__(self, provider, config, api_key, tools, history, user_text):
        try:
            import anthropic
        except ImportError as e:
            raise AgentError("Il pacchetto Python 'anthropic' non è installato "
                             "nel container Odoo.") from e
        self.anthropic = anthropic
        self.api_key = api_key
        self.prefixes = PROVIDERS[provider]['key_prefixes']

        # Le key non legate a un workspace (es. service key) richiedono
        # l'header anthropic-workspace-id: lo prendiamo da ANTHROPIC_WORKSPACE_ID.
        headers = {}
        workspace_id = os.environ.get('ANTHROPIC_WORKSPACE_ID', '').strip()
        if workspace_id:
            headers['anthropic-workspace-id'] = workspace_id
        self.client = anthropic.Anthropic(api_key=api_key, default_headers=headers)

        self.messages = list(history) + [{'role': 'user', 'content': user_text}]
        model = config['model']
        self.request = {
            'model': model,
            'max_tokens': MAX_TOKENS,
            'system': config['system_prompt'],
            'thinking': {'type': 'adaptive'},
            'output_config': {'effort': config['effort']},
            'cache_control': {'type': 'ephemeral'},
        }
        if tools:
            self.request['tools'] = [{
                'name': t.name, 'description': t.description, 'input_schema': t.schema,
            } for t in tools]
        if model in FALLBACK_MODELS:
            self.request['betas'] = [FALLBACK_BETA]
            self.request['fallbacks'] = 'default'

    def _hint(self):
        return key_hint(self.api_key, self.prefixes)

    def step(self):
        anthropic = self.anthropic
        try:
            response = self.client.beta.messages.create(messages=self.messages, **self.request)
        except anthropic.AuthenticationError as e:
            raise AgentError(f"API key Anthropic non valida. {self._hint()}") from e
        except anthropic.PermissionDeniedError as e:
            raise AgentError(f"API key Anthropic senza permessi: {e.message} {self._hint()}") from e
        except anthropic.NotFoundError as e:
            raise AgentError(f"Modello Claude '{self.request['model']}' non trovato: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise AgentError("Limite di richieste Anthropic raggiunto, riprova tra poco.") from e
        except anthropic.BadRequestError as e:
            msg = f"Richiesta non valida: {e.message}"
            text = (e.message or '').lower()
            if 'api key' in text or 'workspace' in text:
                msg += f" {self._hint()}"
            raise AgentError(msg) from e
        except anthropic.APIStatusError as e:
            raise AgentError(f"Errore API Anthropic ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AgentError("Impossibile contattare l'API Anthropic.") from e

        # Il contenuto va rimandato invariato (thinking, fallback, tool_use...).
        self.messages.append({'role': 'assistant',
                              'content': [b.to_dict() for b in response.content]})
        text = '\n\n'.join(b.text for b in response.content if b.type == 'text').strip()
        calls = [ToolCall(b.id, b.name, b.input if isinstance(b.input, dict) else {})
                 for b in response.content if b.type == 'tool_use']

        if response.stop_reason == 'refusal':
            return Step(text, stop='refusal')
        if response.stop_reason == 'max_tokens':
            return Step(text, stop='max_tokens')
        if response.stop_reason == 'tool_use' and calls:
            return Step(text, calls, stop='tool')
        return Step(text)

    def add_results(self, results):
        # Tutti i tool_result in un unico messaggio utente.
        self.messages.append({'role': 'user', 'content': [{
            'type': 'tool_result', 'tool_use_id': call.id,
            'content': [{'type': 'text', 'text': output}], 'is_error': is_error,
        } for call, output, is_error in results]})

    def close_interrupted(self, text):
        self.messages.append({'role': 'assistant', 'content': [{'type': 'text', 'text': text}]})

    def history(self):
        return self.messages
