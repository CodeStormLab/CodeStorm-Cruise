"""Passaggio al provider LLM configurabile.

* il vecchio parametro ``model`` diventa ``model_<provider>`` (in base al
  prefisso del nome) e il provider attivo diventa Gemini;
* rimuove la vecchia API key Anthropic salvata nelle impostazioni (le key
  ora stanno solo nel file .env);
* le conversazioni esistenti con uno storico API sono state create con Claude.
"""

PREFIX = 'codestorm_cruise_assistant.'


def migrate(cr, version):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [PREFIX + 'model'])
    row = cr.fetchone()
    if row and row[0]:
        provider = 'anthropic' if row[0].startswith('claude') else 'gemini'
        cr.execute("""
            INSERT INTO ir_config_parameter (key, value, create_date, write_date)
            VALUES (%s, %s, now(), now())
            ON CONFLICT (key) DO NOTHING
        """, [PREFIX + 'model_' + provider, row[0]])
    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_date, write_date)
        VALUES (%s, 'gemini', now(), now())
        ON CONFLICT (key) DO NOTHING
    """, [PREFIX + 'provider'])
    cr.execute("DELETE FROM ir_config_parameter WHERE key IN %s",
               [(PREFIX + 'model', PREFIX + 'anthropic_api_key')])
    cr.execute("""
        UPDATE ir_config_parameter SET value = 'high'
         WHERE key = %s AND value IN ('xhigh', 'max')
    """, [PREFIX + 'effort'])
    cr.execute("""
        UPDATE cruise_assistant_conversation SET api_provider = 'anthropic'
         WHERE api_provider IS NULL AND COALESCE(api_history, '[]') <> '[]'
    """)
