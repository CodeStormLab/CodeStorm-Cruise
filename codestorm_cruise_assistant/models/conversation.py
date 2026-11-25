import json

from odoo import api, fields, models


class CruiseAssistantConversation(models.Model):
    _name = 'cruise.assistant.conversation'
    _description = 'Conversazione assistente'
    _order = 'write_date desc, id desc'

    name = fields.Char('Titolo', required=True, default='Nuova conversazione')
    user_id = fields.Many2one(
        'res.users', 'Utente', required=True, index=True,
        default=lambda self: self.env.user, ondelete='cascade')
    message_ids = fields.One2many(
        'cruise.assistant.message', 'conversation_id', 'Messaggi')
    # Trascrizione completa per l'API Claude (blocchi thinking, tool_use,
    # tool_result...), da rimandare invariata a ogni turno.
    api_history = fields.Text('Storico API', default='[]')

    def get_api_history(self):
        self.ensure_one()
        try:
            return json.loads(self.api_history or '[]')
        except ValueError:
            return []

    def to_summary(self):
        return [{
            'id': c.id,
            'name': c.name,
            'write_date': fields.Datetime.to_string(c.write_date),
        } for c in self]


class CruiseAssistantMessage(models.Model):
    _name = 'cruise.assistant.message'
    _description = 'Messaggio assistente'
    _order = 'id'

    conversation_id = fields.Many2one(
        'cruise.assistant.conversation', required=True, index=True,
        ondelete='cascade')
    role = fields.Selection(
        [('user', 'Utente'), ('assistant', 'Assistente'), ('tool', 'Tool')],
        required=True)
    content = fields.Text()
    tool_name = fields.Char()
    is_error = fields.Boolean()

    @api.model
    def to_client(self, records):
        return [{
            'id': m.id,
            'role': m.role,
            'content': m.content or '',
            'tool_name': m.tool_name or '',
            'is_error': m.is_error,
        } for m in records]
