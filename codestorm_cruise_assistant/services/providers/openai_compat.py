"""Adattatore per i provider con API compatibile OpenAI Chat Completions
(Groq, Mistral), tramite l'SDK ``openai``."""
import json

from ..common import AgentError, Step, ToolCall, key_hint
from . import PROVIDERS

BASE_URLS = {
    'groq': 'https://api.groq.com/openai/v1',
    'mistral': 'https://api.mistral.ai/v1',
}
# Provider che vogliono il nome della funzione anche nel messaggio "tool".
TOOL_NAME_IN_RESULT = {'groq', 'mistral'}


def _text(content):
    """Il contenuto può essere una stringa o una lista di blocchi."""
    if isinstance(content, str):
        return content
    chunks = []
    for c in content or []:
        if isinstance(c, dict):
            if c.get('type') == 'text':
                chunks.append(c.get('text', ''))
        elif getattr(c, 'type', None) == 'text':
            chunks.append(getattr(c, 'text', ''))
    return '\n'.join(chunks)


class OpenAICompatSession:
    def __init__(self, provider, config, api_key, tools, history, user_text):
        try:
            import openai
        except ImportError as e:
            raise AgentError("Il pacchetto Python 'openai' non è installato "
                             "nel container Odoo.") from e
        self.openai = openai
        self.provider = provider
        self.label = PROVIDERS[provider]['label']
        self.prefixes = PROVIDERS[provider]['key_prefixes']
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key, base_url=BASE_URLS[provider])
        self.system = config['system_prompt']
        self.messages = list(history) + [{'role': 'user', 'content': user_text}]

        model = config['model']
        self.request = {'model': model}
        if tools:
            self.request['tools'] = [{'type': 'function', 'function': {
                'name': t.name, 'description': t.description, 'parameters': t.schema,
            }} for t in tools]
        # Solo i modelli gpt-oss (Groq) accettano reasoning_effort.
        if 'gpt-oss' in model:
            self.request['reasoning_effort'] = config['effort']

    def _hint(self):
        return key_hint(self.api_key, self.prefixes)

    def step(self):
        openai = self.openai
        model = self.request['model']
        try:
            response = self.client.chat.completions.create(
                messages=[{'role': 'system', 'content': self.system}] + self.messages,
                **self.request)
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            raise AgentError(f"API key {self.label} non valida o senza permessi: "
                             f"{e.message} {self._hint()}") from e
        except openai.NotFoundError as e:
            raise AgentError(f"Modello {self.label} '{model}' non trovato: {e.message}") from e
        except openai.RateLimitError as e:
            raise AgentError(f"Limite di richieste {self.label} raggiunto, riprova tra poco.") from e
        except openai.BadRequestError as e:
            msg = f"Richiesta non valida: {e.message}"
            if 'api key' in (e.message or '').lower():
                msg += f" {self._hint()}"
            raise AgentError(msg) from e
        except openai.APIStatusError as e:
            raise AgentError(f"Errore API {self.label} ({e.status_code}): {e.message}") from e
        except openai.APIConnectionError as e:
            raise AgentError(f"Impossibile contattare l'API {self.label}.") from e

        if not response.choices:
            return Step(stop='refusal')
        choice = response.choices[0]
        msg = choice.message
        text = _text(msg.content).strip()

        calls, stored_calls = [], []
        for tc in msg.tool_calls or []:
            raw = tc.function.arguments or '{}'
            try:
                args = json.loads(raw)
            except ValueError:
                args = {}
            calls.append(ToolCall(tc.id, tc.function.name, args if isinstance(args, dict) else {}))
            stored_calls.append({'id': tc.id, 'type': 'function',
                                 'function': {'name': tc.function.name, 'arguments': raw}})

        stored = {'role': 'assistant'}
        if text or not stored_calls:
            stored['content'] = text
        if stored_calls:
            stored['tool_calls'] = stored_calls
        self.messages.append(stored)

        if choice.finish_reason == 'content_filter':
            return Step(text, stop='refusal')
        if choice.finish_reason == 'length':
            return Step(text, stop='max_tokens')
        if calls:
            return Step(text, calls, stop='tool')
        return Step(text)

    def add_results(self, results):
        for call, output, is_error in results:
            message = {'role': 'tool', 'tool_call_id': call.id,
                       'content': f'Errore: {output}' if is_error else output}
            if self.provider in TOOL_NAME_IN_RESULT:
                message['name'] = call.name
            self.messages.append(message)

    def close_interrupted(self, text):
        self.messages.append({'role': 'assistant', 'content': text})

    def history(self):
        return self.messages
