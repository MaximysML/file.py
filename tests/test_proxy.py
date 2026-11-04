import unittest
from aiohttp.test_utils import AioHTTPTestCase
from proxy_server import create_app, assistant_message, build_prompt


class ProxyTests(AioHTTPTestCase):
    async def get_application(self):
        self.sent = []
        async def exchange(prompt):
            self.sent.append(prompt)
            return 'Ответ'
        return create_app(exchange, 'test-key')

    async def test_auth(self):
        response = await self.client.get('/v1/models')
        self.assertEqual(response.status, 401)

    async def test_completion(self):
        response = await self.client.post('/v1/chat/completions',
            headers={'Authorization': 'Bearer test-key'},
            json={'model': 'discord-relay', 'messages': [{'role': 'user', 'content': 'Привет'}]})
        self.assertEqual(response.status, 200)
        data = await response.json()
        self.assertEqual(data['choices'][0]['message']['content'], 'Ответ')
        self.assertIn('Привет', self.sent[0])
        self.assertIn('tools=', self.sent[0])

    async def test_invalid(self):
        for body in ({'stream': True}, {'messages': []}, {'messages': [{'role': 'user', 'content': []}]}):
            response = await self.client.post('/v1/chat/completions', headers={'Authorization': 'Bearer test-key'}, json=body)
            self.assertEqual(response.status, 400)


class ToolTests(unittest.TestCase):
    def test_tool_envelope(self):
        tools = [{'type': 'function', 'function': {'name': 'open_url'}}]
        message = assistant_message('{"tool_calls":[{"name":"open_url","arguments":{"url":"https://example.com"}}]}', tools)
        self.assertEqual(message['tool_calls'][0]['function']['name'], 'open_url')
        with self.assertRaises(ValueError):
            assistant_message('{"tool_calls":[{"name":"shell","arguments":{}}]}', tools)

    def test_prompt(self):
        prompt = build_prompt({'messages': [{'role': 'tool', 'content': 'result', 'tool_call_id': '1'}]})
        self.assertIn('tool_call_id', prompt)
