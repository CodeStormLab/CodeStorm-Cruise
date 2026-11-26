"""Adattatore Google Gemini (SDK ``google-genai``)."""
import logging

from ..common import AgentError, Step, ToolCall, key_hint
from . import PROVIDERS

_logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 32000   # su Gemini include anche i token di ragionamento
THINKING_LEVELS = {'low': 'LOW', 'medium': 'MEDIUM', 'high': 'HIGH'}
BLOCKED_FINISH_REASONS = {
    'SAFETY', 'PROHIBITED_CONTENT', 'BLOCKLIST', 'SPII', 'RECITATION', 'IMAGE_SAFETY',
}


class GeminiSession:
    def __init__(self, provider, config, api_key, tools, history, user_text):
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as e:
            raise AgentError("Il pacchetto Python 'google-genai' non è installato "
                             "nel container Odoo.") from e
        self.errors, self.types = errors, types
        self.api_key = api_key
        self.prefixes = PROVIDERS[provider]['key_prefixes']
        self.client = genai.Client(api_key=api_key)
        self.model = config['model']

        self.contents = self._load_history(history)
        self.contents.append(types.Content(role='user', parts=[types.Part(text=user_text)]))

        decls = [types.FunctionDeclaration(
            name=t.name, description=t.description, parameters_json_schema=t.schema,
        ) for t in tools]
        self.config = types.GenerateContentConfig(
            system_instruction=config['system_prompt'],
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(
                thinking_level=THINKING_LEVELS.get(config['effort'], 'MEDIUM')),
            tools=[types.Tool(function_declarations=decls)] if decls else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _load_history(self, history):
        """Ricostruisce i Content salvati; uno storico non valido viene scartato."""
        try:
            contents = [self.types.Content.model_validate(c) for c in history]
        except Exception:
            _logger.info("Cruise assistant: storico Gemini non valido, riparto da zero.")
            return []
        if any(c.role not in ('user', 'model') for c in contents):
            return []
        return contents

    def _is_key_error(self, err):
        status = (getattr(err, 'status', '') or '').upper()
        message = (getattr(err, 'message', '') or '').lower()
        return (err.code in (401, 403)
                or status in ('UNAUTHENTICATED', 'PERMISSION_DENIED')
                or 'api key' in message or 'api_key' in message)

    def step(self):
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=self.contents, config=self.config)
        except self.errors.APIError as e:
            if self._is_key_error(e):
                raise AgentError(f"API key Gemini non valida o senza permessi: {e.message} "
                                 f"{key_hint(self.api_key, self.prefixes)}") from e
            if e.code == 429:
                raise AgentError("Limite di richieste Gemini raggiunto, riprova tra poco.") from e
            if e.code == 404:
                raise AgentError(f"Modello Gemini '{self.model}' non trovato: {e.message}") from e
            if e.code == 400:
                raise AgentError(f"Richiesta non valida: {e.message}") from e
            raise AgentError(f"Errore API Gemini ({e.code}): {e.message}") from e

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            block = getattr(response.prompt_feedback, 'block_reason', None)
            return Step(stop='refusal', detail=str(block or ''))

        # Il contenuto va rimandato invariato (thought signature incluse).
        content = candidate.content
        content.role = 'model'
        self.contents.append(content)

        parts = content.parts or []
        text = '\n\n'.join(p.text for p in parts if p.text and not p.thought).strip()
        calls = [ToolCall(p.function_call.id, p.function_call.name, dict(p.function_call.args or {}))
                 for p in parts if p.function_call]
        finish = getattr(candidate.finish_reason, 'name', str(candidate.finish_reason or ''))
        if finish in BLOCKED_FINISH_REASONS:
            return Step(text, stop='refusal')
        if finish == 'MAX_TOKENS':
            return Step(text, stop='max_tokens')
        if calls:
            return Step(text, calls, stop='tool')
        return Step(text)

    def add_results(self, results):
        types = self.types
        # Tutte le function response in un unico messaggio utente.
        self.contents.append(types.Content(role='user', parts=[
            types.Part(function_response=types.FunctionResponse(
                id=call.id, name=call.name,
                response={'error': output} if is_error else {'output': output},
            )) for call, output, is_error in results]))

    def close_interrupted(self, text):
        self.contents.append(self.types.Content(role='model', parts=[self.types.Part(text=text)]))

    def history(self):
        return [c.model_dump(mode='json', exclude_none=True) for c in self.contents]
