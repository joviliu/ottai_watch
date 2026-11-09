"""Import a private connection file before launching the GUI; never print credentials."""
from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import stat
import sys
import uuid


def configure(source: Path, destination: Path):
    parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 16384:
                raise ValueError('unsafe input')
            data = stream.read(16385)
    finally:
        os.close(parent)
    if len(data) > 16384:
        raise ValueError('oversize input')
    configuration = json.loads(data)
    address, token = configuration.get('baseURL'), configuration.get('readToken')
    if not isinstance(address, str) or not isinstance(token, str):
        raise ValueError('invalid structure')
    parsed = urlsplit(address)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('invalid address')
    if not token or len(token.encode()) > 8192 or any(not 32 < ord(char) < 127 for char in token):
        raise ValueError('invalid token')
    encoded = json.dumps({'baseURL': address.rstrip('/'), 'readToken': token}, separators=(',', ':')).encode()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.connection-' + uuid.uuid4().hex + '.tmp'
    try:
        if os.fstat(folder).st_uid != os.geteuid():
            raise ValueError('wrong directory owner')
        os.fchmod(folder, 0o700)
        try:
            current = os.stat(destination.name, dir_fd=folder, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and (not stat.S_ISREG(current.st_mode) or current.st_uid != os.geteuid()):
            raise ValueError('unsafe destination')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination.name, src_dir_fd=folder, dst_dir_fd=folder)
    finally:
        try:
            os.unlink(temporary, dir_fd=folder)
        except FileNotFoundError:
            pass
        os.close(folder)


if __name__ == '__main__':
    try:
        if len(sys.argv) > 2:
            raise ValueError('expected at most one private file')
        home = Path.home()
        destination = home / 'Library/Application Support/OttaiMirror/connection.json'
        source = Path(sys.argv[1]) if len(sys.argv) == 2 else destination
        configure(source, destination)
        configure(destination, home / 'Library/Containers/com.joviliu.ottai.mirror.widget/Data/Library/Application Support/OttaiMirror/connection.json')
    except Exception:
        print('Private configuration import failed; check structure, ownership, permissions and symlinks.', file=sys.stderr)
        sys.exit(1)
    print('Private configuration saved before GUI launch.')
