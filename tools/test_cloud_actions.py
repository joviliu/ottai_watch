"""Run the production Android HTTP transport with tiny host stubs; no network or credentials."""
import os
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
java_bin = pathlib.Path(os.environ['JDK']) / 'bin' if os.environ.get('JDK') else pathlib.Path('')
javac = str(java_bin / 'javac') if os.environ.get('JDK') else 'javac'
java = str(java_bin / 'java') if os.environ.get('JDK') else 'java'
sources = [root / 'android/src/main/java/com/example/glucosewatch6/CloudActions.java',
           *sorted((root / 'android/test/cloud_actions').rglob('*.java'))]
with tempfile.TemporaryDirectory(prefix='ottai-cloud-actions-') as output:
    subprocess.run([javac, '--release', '8', '-d', output, *map(str, sources)], check=True)
    subprocess.run([java, '-cp', output, 'com.example.glucosewatch6.CloudActionsTest'], check=True, timeout=30)
