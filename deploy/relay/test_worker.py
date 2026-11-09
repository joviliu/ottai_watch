import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('worker', Path(__file__).with_name('worker.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_reservations_survive_restart_and_cap_spend(self):
        with tempfile.TemporaryDirectory() as directory:
            first = module.Worker.__new__(module.Worker)
            first.state = Path(directory)/'state.json'
            self.assertTrue(first.reserve('a'))
            second = module.Worker.__new__(module.Worker)
            second.state = first.state
            self.assertFalse(second.reserve('a'))
            self.assertTrue(second.reserve('b'))
            self.assertFalse(second.reserve('c'))
            self.assertEqual(os.stat(str(first.state)).st_mode & 0o777, 0o600)

    def test_only_stateless_responses_reach_provider_once(self):
        class Response:
            code = 200
            def read(self, n): return b'{"ok":true}'
        class Opener:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                self.url = request.full_url
                return Response()
        with tempfile.TemporaryDirectory() as directory:
            worker = module.Worker.__new__(module.Worker)
            worker.state = Path(directory)/'state.json'
            worker.key = 'test-key'
            worker.opener = Opener()
            outputs = []
            worker.relay = lambda action, value: outputs.append(value)
            headers = {'X-AI-Provider-'+k: v for k, v in {
                'Job': 'a'*64, 'Lease': 'b'*48, 'Request': 'c'*64,
                'Path': '/v1/responses', 'Type': 'application/json',
                'Deadline': str(int(time.time()*1000)+30000)}.items()}
            worker.execute(headers, b'{"store":true}')
            self.assertEqual(worker.opener.calls, 0)
            worker.execute(headers, b'{"store":false}')
            worker.execute(headers, b'{"store":false}')
            self.assertEqual(worker.opener.calls, 1)
            self.assertEqual(worker.opener.url, 'https://api.openai.com/v1/responses')
            self.assertIn('error', outputs[-1])


if __name__ == '__main__': unittest.main()
