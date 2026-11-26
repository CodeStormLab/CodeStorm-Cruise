{
    'name': 'Codestorm Cruise Assistant',
    'version': '19.0.1.2.0',
    'summary': 'Chat AI (Claude, Gemini, Groq, Mistral) collegata al server MCP di Odoo',
    'description': """
Assistente conversazionale per Odoo.

* Pagina web di chat su /cruise_assistant
* Il modello LLM scelto nelle impostazioni usa i tool esposti dal modulo mcp_server (endpoint /mcp)
* Conversazioni salvate per utente
    """,
    'author': 'Codestorm',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['base', 'base_setup', 'web', 'mcp_server'],
    'external_dependencies': {'python': ['anthropic', 'google.genai', 'openai']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/conversation_views.xml',
        'views/chat_templates.xml',
        'views/home_templates.xml',
        'views/menus.xml',
    ],
    'application': True,
    'installable': True,
}
