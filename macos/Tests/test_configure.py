from pathlib import Path
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('configure', Path(__file__).resolve().parents[1] / 'configure.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigureTests(unittest.TestCase):
    def test_private_atomic_import_and_input_policy(self):
        with tempfile.TemporaryDirectory(prefix='ottai-import-test-') as folder:
            base = Path(folder)
            source, target = base / 'input.json', base / 'private' / 'connection.json'
            payload = {'baseURL': 'https://example.invalid/ottai/', 'readToken': 'test-read-only-token'}
            source.write_text(json.dumps(payload))
            source.chmod(0o600)
            module.configure(source, target)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertEqual(json.loads(target.read_text()), dict(payload, baseURL=payload['baseURL'].rstrip('/')))
            link = base / 'link.json'
            link.symlink_to(source)
            with self.assertRaises(OSError): module.configure(link, target)
            target.unlink(); target.symlink_to(source)
            with self.assertRaises(ValueError): module.configure(source, target)
            target.unlink(); source.chmod(0o644)
            with self.assertRaises(ValueError): module.configure(source, target)
            source.chmod(0o600); source.write_bytes(b'A' * 16385)
            with self.assertRaises(ValueError): module.configure(source, target)

    def test_cli_provisions_both_processes_and_reuses_private_connection(self):
        with tempfile.TemporaryDirectory(prefix='ottai-install-test-') as folder:
            home = Path(folder)
            source = home / 'input.json'
            source.write_text(json.dumps({'baseURL': 'https://example.invalid/ottai', 'readToken': 'test-read-only-token'}))
            source.chmod(0o600)
            script = Path(__file__).resolve().parents[1] / 'configure.py'
            env = dict(os.environ, HOME=folder)
            for args in [[str(source)], []]:
                output = subprocess.run([sys.executable, str(script)] + args, env=env, capture_output=True, text=True)
                self.assertEqual(output.returncode, 0)
                self.assertNotIn('test-read-only-token', output.stdout + output.stderr)
                host = home / 'Library/Application Support/OttaiMirror/connection.json'
                widget = home / 'Library/Containers/com.joviliu.ottai.mirror.widget/Data/Library/Application Support/OttaiMirror/connection.json'
                self.assertEqual(host.read_bytes(), widget.read_bytes())
                self.assertEqual(stat.S_IMODE(widget.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(widget.parent.stat().st_mode), 0o700)

    def test_analysis_capability_is_never_provisioned_to_widget(self):
        with tempfile.TemporaryDirectory(prefix='ottai-capability-test-') as folder:
            base=Path(folder);source=base/'input.json';host=base/'host/connection.json';widget=base/'widget/connection.json'
            source.write_text(json.dumps({'baseURL':'https://example.invalid','readToken':'read-only','analysisToken':'a'*32}));source.chmod(0o600)
            module.configure(source,host)
            module.configure(host,widget,include_analysis=False)
            self.assertIn('analysisToken',json.loads(host.read_bytes()))
            self.assertNotIn('analysisToken',json.loads(widget.read_bytes()))


if __name__ == '__main__':
    unittest.main()
