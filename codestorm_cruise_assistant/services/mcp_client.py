"""Client MCP minimale (Streamable HTTP, JSON-RPC 2.0) per l'endpoint /mcp
del modulo ``mcp_server``.

Il server è stateless e risponde in JSON; gestiamo comunque anche una
risposta ``text/event-stream`` per robustezza.
"""
import itertools
import json
import logging

import requests

_logger = logging.getLogger(__name__)

PROTOCOL_VERSION = '2025-11-25'
CLIENT_INFO = {'name': 'codestorm-cruise-assistant', 'version': '1.0.0'}


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, url, api_key, timeout=60):
        if not url:
            raise McpError("URL del server MCP non configurato.")
        if not api_key:
            raise McpError("API key MCP non configurata.")
        self.url = url
        self.timeout = timeout
        self._ids = itertools.count(1)
        self._protocol_version = None
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'Authorization': f'Bearer {api_key}',
        })

    # ------------------------------------------------------------------
    def _post(self, payload):
        headers = {}
        if self._protocol_version:
            headers['MCP-Protocol-Version'] = self._protocol_version
        try:
            resp = self._session.post(
                self.url, data=json.dumps(payload), headers=headers,
                timeout=self.timeout)
        except requests.RequestException as e:
            raise McpError(f"Server MCP non raggiungibile: {e}") from e
        if resp.status_code == 202:
            return None
        if resp.status_code == 401:
            raise McpError("Autenticazione MCP fallita: controlla l'API key "
                           "e che l'utente sia nel gruppo MCP User.")
        if resp.status_code >= 400 and not resp.content:
            raise McpError(f"Errore HTTP {resp.status_code} dal server MCP.")
        return self._parse(resp)

    @staticmethod
    def _parse(resp):
        ctype = resp.headers.get('Content-Type', '')
        if 'text/event-stream' in ctype:
            data = None
            for line in resp.text.splitlines():
                if line.startswith('data:'):
                    data = json.loads(line[5:].strip())
            if data is None:
                raise McpError("Risposta SSE vuota dal server MCP.")
            return data
        try:
            return resp.json()
        except ValueError as e:
            raise McpError(
                f"Risposta non valida dal server MCP (HTTP {resp.status_code})."
            ) from e

    def _request(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'id': next(self._ids), 'method': method}
        if params is not None:
            payload['params'] = params
        data = self._post(payload) or {}
        if 'error' in data:
            err = data['error']
            raise McpError(f"{err.get('message')} (codice {err.get('code')})")
        return data.get('result', {})

    def _notify(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        self._post(payload)

    # ------------------------------------------------------------------
    def initialize(self):
        result = self._request('initialize', {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {},
            'clientInfo': CLIENT_INFO,
        })
        self._protocol_version = result.get('protocolVersion', PROTOCOL_VERSION)
        self._notify('notifications/initialized')
        return result

    def list_tools(self):
        tools, cursor = [], None
        while True:
            result = self._request('tools/list', {'cursor': cursor} if cursor else {})
            tools.extend(result.get('tools', []))
            cursor = result.get('nextCursor')
            if not cursor:
                return tools

    def call_tool(self, name, arguments):
        return self._request('tools/call', {'name': name, 'arguments': arguments or {}})
