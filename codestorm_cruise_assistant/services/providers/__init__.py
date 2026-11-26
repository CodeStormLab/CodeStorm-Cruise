"""Registro dei provider LLM. Gli SDK vengono importati solo quando il
provider viene usato, così le impostazioni funzionano anche senza tutti
i pacchetti installati."""

PROVIDERS = {
    'anthropic': {
        'label': 'Anthropic Claude',
        'env': 'ANTHROPIC_API_KEY',
        'key_prefixes': ('sk-ant-',),
        'default_model': 'claude-opus-5-5',
    },
    'gemini': {
        'label': 'Google Gemini',
        'env': 'GEMINI_API_KEY',
        'key_prefixes': ('AIza', 'AQ.'),
        'default_model': 'gemini-3.8-flash',
    },
    'groq': {
        'label': 'Groq',
        'env': 'GROQ_API_KEY',
        'key_prefixes': ('gsk_',),
        'default_model': 'openai/gpt-oss-120b',
    },
    'mistral': {
        'label': 'Mistral',
        'env': 'MISTRAL_API_KEY',
        'key_prefixes': (),
        'default_model': 'mistral-large-latest',
    },
}
DEFAULT_PROVIDER = 'gemini'


def create_session(provider, config, api_key, tools, history, user_text):
    if provider == 'anthropic':
        from .anthropic_provider import AnthropicSession as cls
    elif provider == 'gemini':
        from .gemini_provider import GeminiSession as cls
    else:
        from .openai_compat import OpenAICompatSession as cls
    return cls(provider, config, api_key, tools, history, user_text)
