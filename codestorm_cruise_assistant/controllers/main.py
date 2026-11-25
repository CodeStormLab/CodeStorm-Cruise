import json
import logging

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from ..models.res_config_settings import (
    CRUISE_CARDS_PROMPT, DEFAULT_SYSTEM_PROMPT, PARAM_PREFIX,
)
from ..services.agent import AgentError, run_turn

_logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 20000


class CruiseAssistantController(http.Controller):

    # ------------------------------------------------------------------
    # Pagina web
    # ------------------------------------------------------------------
    @http.route('/cruise_assistant', type='http', auth='user', methods=['GET'])
    def chat_page(self, **kw):
        return request.render('codestorm_cruise_assistant.chat_page', {
            'user_name': request.env.user.name,
        })

    @http.route('/cruise_assistant/home', type='http', auth='user', methods=['GET'])
    def home_page(self, **kw):
        return request.render('codestorm_cruise_assistant.home_page', {})

    # ------------------------------------------------------------------
    # API JSON-RPC usate dalla pagina
    # ------------------------------------------------------------------
    def _conversation(self, conversation_id):
        conv = request.env['cruise.assistant.conversation'].browse(int(conversation_id)).exists()
        if not conv:
            raise UserError("Conversazione non trovata.")
        conv.check_access('read')
        return conv

    @http.route('/cruise_assistant/conversations', type='jsonrpc', auth='user')
    def conversations(self):
        convs = request.env['cruise.assistant.conversation'].search(
            [('user_id', '=', request.env.uid)], limit=100)
        return convs.to_summary()

    @http.route('/cruise_assistant/messages', type='jsonrpc', auth='user')
    def messages(self, conversation_id):
        conv = self._conversation(conversation_id)
        return {
            'conversation': conv.to_summary()[0],
            'messages': request.env['cruise.assistant.message'].to_client(conv.message_ids),
        }

    @http.route('/cruise_assistant/delete', type='jsonrpc', auth='user')
    def delete(self, conversation_id):
        self._conversation(conversation_id).unlink()
        return True

    @http.route('/cruise_assistant/send', type='jsonrpc', auth='user')
    def send(self, message, conversation_id=None):
        text = (message or '').strip()
        if not text:
            raise UserError("Messaggio vuoto.")
        if len(text) > MAX_MESSAGE_CHARS:
            raise UserError("Messaggio troppo lungo.")

        Conversation = request.env['cruise.assistant.conversation']
        conv = self._conversation(conversation_id) if conversation_id else Conversation

        try:
            result = run_turn(self._config(), conv.get_api_history() if conv else [], text)
        except AgentError as e:
            return {'error': str(e)}
        except Exception:
            _logger.exception("Errore inatteso nel Cruise Assistant")
            return {'error': "Errore inatteso, controlla il log del server."}

        if not conv:
            conv = Conversation.create({'name': text[:60] + ('…' if len(text) > 60 else '')})
        Message = request.env['cruise.assistant.message']
        new_msgs = Message.create(
            [{'conversation_id': conv.id, 'role': 'user', 'content': text}]
            + [dict(ev, conversation_id=conv.id) for ev in result.events])
        conv.write({
            'api_history': json.dumps(result.history, ensure_ascii=False, default=str),
        })
        return {
            'conversation': conv.to_summary()[0],
            'messages': Message.to_client(new_msgs),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _config():
        icp = request.env['ir.config_parameter'].sudo()

        def get(key, default=''):
            return icp.get_param(PARAM_PREFIX + key) or default

        return {
            'anthropic_api_key': get('anthropic_api_key'),
            'model': get('model', 'claude-opus-5-5'),
            'effort': get('effort', 'medium'),
            'mcp_url': get('mcp_url', 'http://localhost:8069/mcp'),
            'mcp_api_key': get('mcp_api_key'),
            'system_prompt': '%s\n\n%s\n\nUtente corrente: %s. Data odierna: %s.' % (
                get('system_prompt', DEFAULT_SYSTEM_PROMPT),
                CRUISE_CARDS_PROMPT,
                request.env.user.name,
                fields.Date.context_today(request.env.user),
            ),
        }
