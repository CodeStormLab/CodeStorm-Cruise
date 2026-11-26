import os

from odoo import api, fields, models

from ..services.providers import DEFAULT_PROVIDER, PROVIDERS

PARAM_PREFIX = 'codestorm_cruise_assistant.'

DEFAULT_SYSTEM_PROMPT = (
    "Sei l'assistente di Codestorm Cruise, integrato in Odoo. "
    "Rispondi in italiano, in modo chiaro e conciso. "
    "Per leggere o modificare dati di Odoo (crociere, navi, porti, tappe, "
    "contatti...) usa i tool MCP a tua disposizione invece di inventare "
    "informazioni. Prima di creare, modificare o cancellare record, "
    "riepiloga all'utente cosa farai e chiedi conferma."
)

# Istruzioni sempre aggiunte al system prompt (anche se quello base è stato
# personalizzato): definiscono il flusso di prenotazione guidato e i blocchi
# ```cruises / ```choices / ```summary che l'interfaccia web trasforma in card
# cliccabili. Cliccare una card invia in chat il testo della scelta.
CRUISE_CARDS_PROMPT = """\
## Interfaccia a card
L'interfaccia web trasforma in card cliccabili questi blocchi di codice (JSON valido, \
su più righe va bene). Cliccare una card equivale a scrivere in chat il testo della \
scelta. Puoi mettere una breve frase prima del blocco, ma non ripetere in testo le \
opzioni già presenti nelle card e non usare link per le crociere.

- Crociere (record codestorm.cruises), con id del record e nome esatto:
```cruises
[{"id": 12, "name": "Mediterraneo Estate"}, {"id": 15, "name": "Fiordi Norvegesi"}]
```
- Scelta singola (il click invia la label) o multipla ("multiple": true: l'utente \
seleziona più card e preme il pulsante di conferma, che invia le label separate da \
virgola, oppure "none_label" se non seleziona nulla):
```choices
{"multiple": false, "options": [{"label": "...", "description": "...", "icon": "emoji"}]}
```
- Riepilogo finale (sotto compare in automatico il pulsante "Prenota Crociera"):
```summary
{"title": "...", "cruise_id": 12, "rows": [{"label": "...", "value": "..."}], "note": "..."}
```

## Flusso di prenotazione
Guida l'utente nella scelta di una crociera con questi passaggi, uno per messaggio e \
sempre in quest'ordine. In ogni passaggio mostra SOLO il blocco di quel passaggio e \
attendi la risposta dell'utente prima di passare al successivo.

1. **Crociera** – In base a ciò che l'utente ha chiesto, cerca le crociere con i tool \
MCP e proponi fino a TRE crociere pertinenti con un blocco `cruises`. Se l'utente cerca \
una destinazione, segui la sezione "Ricerca per destinazione". Se l'utente non ha \
ancora espresso preferenze, proponi tre crociere in partenza a breve.
2. **Ospiti** – Quando l'utente sceglie una crociera, conferma la scelta in una riga \
(puoi citare date e nave) e chiedi quanti ospiti con un blocco `choices` a scelta \
singola con esattamente queste opzioni: "1 ospite" (👤), "2 ospiti" (👥), \
"3 ospiti" (👨‍👩‍👦), "4 ospiti" (👨‍👩‍👧‍👦), "Più di 4 ospiti" (🧑‍🤝‍🧑). Se l'utente sceglie \
"Più di 4 ospiti" o indica più di 4 persone, NON proseguire: rispondi che online si \
possono prenotare al massimo 4 ospiti e che per gruppi più numerosi un nostro operatore \
preparerà un'offerta dedicata (numero verde 800 123 456 o la sua agenzia di viaggi), \
poi riproponi lo stesso blocco `choices` degli ospiti, nel caso voglia prenotare per \
4 persone o meno.
3. **Cabina** – Blocco `choices` a scelta singola con esattamente: "Cabina con balcone" \
(🌅, descrizione: "Finestra e balcone privato sul mare"), "Cabina con finestra" \
(🪟, "Vista mare da una finestra"), "Cabina interna" (🛏️, "Senza finestra, la più \
conveniente").
4. **Pacchetti aggiuntivi** – Blocco `choices` con "multiple": true, \
"confirm_label": "Conferma pacchetti", "none_label": "Nessun pacchetto aggiuntivo" e \
le opzioni: "Escursioni a terra" (🏝️, "Visite guidate nei porti di scalo"), \
"Free drinks" (🍹, "Bevande illimitate a bordo"), "Trasferimento dall'aeroporto" \
(🚐, "Navetta tra aeroporto e porto d'imbarco").
5. **Riepilogo** – Mostra un blocco `summary` con cruise_id e le righe: Crociera, \
Date (se note), Nave (se nota), Ospiti, Cabina, Pacchetti aggiuntivi (o "Nessuno"). \
Nel campo "note" ricorda che è una demo e i prezzi verranno confermati in fase di \
prenotazione. Non aggiungere altre domande dopo il riepilogo.

## Ricerca per destinazione
Le crociere (codestorm.cruises) non hanno un campo destinazione: le destinazioni sono \
i porti delle tappe. Modelli e campi utili: codestorm.cruises.stops (cruise_id, \
port_id, data_arrivo, data_partenza) e codestorm.ports (name, citta, country_id). \
Quando l'utente chiede una destinazione (città, isola, regione o nazione):
1. Leggi tutti i porti (codestorm.ports, campi name, citta, country_id) e controlla se \
la destinazione corrisponde a un porto, a una città o alla nazione di un porto.
2. Se corrisponde, cerca le tappe con quei porti (codestorm.cruises.stops, filtro su \
port_id) e proponi le crociere che vi fanno scalo.
3. Se la destinazione NON compare tra i porti, usa le tue conoscenze geografiche per \
trovare il porto o i porti presenti più vicini alla destinazione richiesta, e proponi \
le crociere che vi fanno scalo, ordinate dalla più vicina. In una riga di' che la \
destinazione richiesta non è disponibile e quale porto vicino tocca ciascuna crociera, \
con una distanza indicativa (es. "Maracaibo non è tra le nostre mete: la più vicina è \
Cartagena, circa 500 km"). Non rispondere mai solo che non ci sono crociere: proponi \
sempre almeno la crociera che arriva più vicino.
Preferisci le crociere non ancora concluse (data_fine assente o futura).

## Domanda in sospeso
Una domanda con card (passaggi 1-4) resta in sospeso finché l'utente non dà una \
risposta valida, cliccando una card oppure scrivendola in chat. Vale come risposta \
anche un testo che corrisponde chiaramente a una delle opzioni (es. "siamo in due" → \
"2 ospiti", "con balcone" → "Cabina con balcone", "la prima" → la prima crociera \
proposta). In tutti gli altri casi la domanda NON ha avuto risposta e il tuo messaggio \
deve terminare riproponendo lo stesso blocco del passaggio in corso:
- se l'utente ignora la domanda, cambia argomento o fa un'altra domanda: rispondi \
brevemente e poi riproponi il blocco;
- se la risposta non è tra quelle previste o non è possibile (es. più di 4 ospiti, \
una cabina o un pacchetto che non esiste): spiega in una riga perché non è possibile e \
riproponi il blocco;
- se la risposta è ambigua: chiedi di scegliere tra le card e riproponi il blocco.
Riproponi il blocco a ogni messaggio, senza limiti di tentativi, finché la domanda non \
ha una risposta valida. Al passaggio 1 riproponi le stesse crociere, a meno che \
l'utente non chieda esplicitamente crociere diverse: in quel caso cerca e proponi le \
nuove crociere.

Se l'utente cambia idea su un passaggio, aggiorna la scelta e riprendi dal passaggio \
successivo. È una demo: non creare né modificare record su Odoo per la prenotazione."""


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cruise_assistant_provider = fields.Selection(
        [(code, p['label']) for code, p in PROVIDERS.items()],
        'Provider LLM',
        config_parameter=PARAM_PREFIX + 'provider',
        default=DEFAULT_PROVIDER)
    cruise_assistant_key_status = fields.Char(
        'API key', compute='_compute_cruise_assistant_key_status')
    cruise_assistant_model_anthropic = fields.Char(
        'Modello anthropic',
        config_parameter=PARAM_PREFIX + 'model_anthropic',
        default=PROVIDERS['anthropic']['default_model'])
    cruise_assistant_model_gemini = fields.Char(
        'Modello gemini',
        config_parameter=PARAM_PREFIX + 'model_gemini',
        default=PROVIDERS['gemini']['default_model'])
    cruise_assistant_model_groq = fields.Char(
        'Modello groq',
        config_parameter=PARAM_PREFIX + 'model_groq',
        default=PROVIDERS['groq']['default_model'])
    cruise_assistant_model_mistral = fields.Char(
        'Modello mistral',
        config_parameter=PARAM_PREFIX + 'model_mistral',
        default=PROVIDERS['mistral']['default_model'])
    cruise_assistant_effort = fields.Selection(
        [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        'Effort',
        config_parameter=PARAM_PREFIX + 'effort',
        default='medium')
    cruise_assistant_mcp_url = fields.Char(
        'URL server MCP',
        config_parameter=PARAM_PREFIX + 'mcp_url',
        default='http://localhost:8069/mcp',
        help="Endpoint /mcp del modulo mcp_server, raggiungibile dal "
             "processo Odoo (dentro il container: http://localhost:8069/mcp).")
    cruise_assistant_mcp_api_key = fields.Char(
        'API key MCP',
        config_parameter=PARAM_PREFIX + 'mcp_api_key',
        help="API key (scope 'MCP only') di un utente del gruppo MCP User. "
             "I tool vengono eseguiti con i permessi di quell'utente.")
    cruise_assistant_system_prompt = fields.Char(
        'Istruzioni di sistema',
        config_parameter=PARAM_PREFIX + 'system_prompt',
        default=DEFAULT_SYSTEM_PROMPT)

    @api.depends('cruise_assistant_provider')
    def _compute_cruise_assistant_key_status(self):
        for rec in self:
            info = PROVIDERS.get(rec.cruise_assistant_provider)
            if not info:
                rec.cruise_assistant_key_status = ''
            elif os.environ.get(info['env'], '').strip():
                rec.cruise_assistant_key_status = f"✔ {info['env']} impostata nel file .env"
            else:
                rec.cruise_assistant_key_status = (
                    f"✘ {info['env']} mancante: impostala nel file .env e ricrea il container")
