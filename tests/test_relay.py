import unittest
from types import SimpleNamespace
from bot_relay import Settings, outgoing_request, parse_request, positive_id, request_text, response_text


class RelayTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(parse_request('/think объясни'), ('think', 'объясни'))
        self.assertEqual(parse_request(' привет '), ('ask', 'привет'))
        self.assertEqual(parse_request('  '), ('', ''))
        self.assertEqual(parse_request('/help'), ('help', ''))

    def test_prompt(self):
        self.assertEqual(request_text(Settings(), 'текст'), 'текст')
        self.assertEqual(request_text(Settings(prompt='Кратко'), 'текст'), 'Кратко\n\nтекст')

    def test_outgoing_commands(self):
        self.assertEqual(outgoing_request(Settings(), 'think', 'задача'), '/think задача')
        self.assertEqual(outgoing_request(Settings(), 'ask', 'вопрос'), '/ask вопрос')
        self.assertEqual(outgoing_request(Settings(prompt='Кратко'), 'think', 'задача'),
                         '/think Кратко\n\nзадача')
        with self.assertRaises(ValueError):
            outgoing_request(Settings(), 'quit', 'текст')

    def test_id(self):
        self.assertEqual(positive_id('123'), 123)
        for value in ('0', '-2', 'abc'):
            with self.assertRaises(ValueError):
                positive_id(value)

    def test_response(self):
        message = SimpleNamespace(content='ответ', embeds=[SimpleNamespace(
            title='заголовок', description='описание', fields=[SimpleNamespace(name='a', value='b')])],
            attachments=[SimpleNamespace(url='https://example.com/file')])
        self.assertEqual(response_text(message), 'ответ\nзаголовок\nописание\na: b\nhttps://example.com/file')
        self.assertIn('без доступного текста', response_text(SimpleNamespace(content='', embeds=[], attachments=[])))


if __name__ == '__main__':
    unittest.main()
