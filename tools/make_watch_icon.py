"""Generate the watch icon as SVG + antialiased PNG, using only Python's standard library."""
import pathlib
import struct
import zlib

SIZE = 192
SCALE = 4
BLUE = (36, 107, 253)
POINTS = [(30, 112), (61, 112), (78, 59), (103, 137), (123, 86), (160, 86)]


def distance_squared(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
    return (x - a[0] - t * dx) ** 2 + (y - a[1] - t * dy) ** 2


def pixel(x, y):
    if (x - 96) ** 2 + (y - 96) ** 2 > 92 ** 2:
        return (0, 0, 0, 0)
    white = (x - 160) ** 2 + (y - 86) ** 2 <= 9 ** 2 or any(
        distance_squared(x, y, a, b) <= 6.5 ** 2 for a, b in zip(POINTS, POINTS[1:]))
    return (*( (255, 255, 255) if white else BLUE ), 255)


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    assets = root / 'assets'
    assets.mkdir(exist_ok=True)
    points = ' '.join(f'{x},{y}' for x, y in POINTS)
    (assets / 'watch-icon.svg').write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">\n'
        '<circle cx="96" cy="96" r="92" fill="#246BFD"/>\n'
        f'<polyline points="{points}" fill="none" stroke="white" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '<circle cx="160" cy="86" r="9" fill="white"/>\n</svg>\n')
    rows = bytearray()
    for y in range(SIZE):
        rows.append(0)
        for x in range(SIZE):
            samples = [pixel(x + (sx + .5) / SCALE, y + (sy + .5) / SCALE)
                       for sy in range(SCALE) for sx in range(SCALE)]
            alpha = sum(p[3] for p in samples)
            rgb = [round(sum(p[c] * p[3] for p in samples) / alpha) if alpha else 0 for c in range(3)]
            rows.extend([*rgb, round(alpha / (SCALE * SCALE))])

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')
    target = root / 'watch/src/common/icon.png'
    target.write_bytes(png)
    assert pixel(0, 0)[3] == 0 and pixel(96, 20) == (*BLUE, 255)
    assert pixel(160, 86) == (255, 255, 255, 255)
    assert len(rows) == SIZE * (1 + SIZE * 4)
    print(target)


if __name__ == '__main__':
    main()
