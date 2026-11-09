"""Consistent private SQLite snapshots; run daily as the ottai-cloud user."""
import datetime
import gzip
import os
import sqlite3
from pathlib import Path

root = Path(os.environ.get('DATABASE_PATH', '/var/lib/ottai-cloud/glucose.sqlite3'))
directory = root.parent / 'backups'
directory.mkdir(mode=0o700, exist_ok=True)
target = directory / ('glucose-' + datetime.date.today().isoformat() + '.sql.gz')
temporary = target.with_suffix('.tmp')
source = sqlite3.connect(root.resolve().as_uri() + '?mode=ro', uri=True)
try:
    source.execute('BEGIN')
    with gzip.open(str(temporary), 'wt', encoding='utf-8') as output:
        for statement in source.iterdump():
            output.write(statement + '\n')
finally:
    source.close()
os.replace(str(temporary), str(target))
target.chmod(0o600)
for stale in sorted(directory.glob('glucose-*.sql.gz'))[:-14]:
    stale.unlink()
