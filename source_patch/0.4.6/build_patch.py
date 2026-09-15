from pathlib import Path
import base64
import binascii
import struct
import subprocess
import sys
import zlib

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.5" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.5 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    if old not in source:
        raise SystemExit(f"Falha ao aplicar patch: {label}")
    source = source.replace(old, new, 1)


source = source.replace('APP_VERSION = "0.4.5"', 'APP_VERSION = "0.4.6"', 1)
if 'APP_VERSION = "0.4.6"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.6")

# ---------------------------------------------------------------------------
# Ícone oficial — pena azul escolhida pelo usuário.
# Guardamos apenas a pequena matriz RGBA da pena e reconstruímos um .ico
# multirresolução durante o build. Assim não precisamos versionar binários.
# ---------------------------------------------------------------------------
ICON_SOURCE_W = 11
ICON_SOURCE_H = 23
ICON_SOURCE_RGBA = base64.b64decode(
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACoaHf8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADAnJ/9PZYD/N0Ng/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACALC/8zLTD/VHKc/zhopf8uPV7/AAAAAAAAAAAAAAAAAAAAAAAAAAAqEBD/SkpM/3OJn/86aab/NGWk/yo1Uv8AAAAAAAAAAAAAAAAAAAAAKxAQ/2BkZv9khK3/RWaT/zRhof8yYZ7/GyU4/wAAAAAAAAAAAAAAAAAAAABNSUr/dpOx/zNgmf8tP2L/MV+d/zFTh/8oFx3/AAAAAAAAAAAAAAAAAAAAAHeCkP89bKf/KkNp/yhGdP80ZaT/JzFQ/wAAAAAAAAAAAAAAAAAAAAAuKCj/Wnqd/zNXi/8VHCv/MVqU/zRlpP8oMlD/AAAAAAAAAAAAAAAADwcH/2Jiaf9Yfav/JCMz/yEqRf80ZaT/NGWk/yEXH/8AAAAAAAAAAAAAAABDPkD/kKnD/0lhhv8MChH/L1qS/zRlpP8vSXL/GwoK/wAAAAAAAAAAIQwN/6Opq/86aaH/HSY+/yIzT/80ZaT/M2Gb/xYSHP8AAAAAAAAAAAAAAAAyIyb/oLC+/zNakf8VFCD/LVqS/zRlpP8sOVr/GQkM/wAAAAAAAAAAAAAAAFBLTf95k7L/LE+B/xwbJv8wX5v/M12U/xsZJv8AAAAAAAAAAAAAAAAAAAAAZGBg/2+Nsf8oPF//HzZV/zNjn/8qP2P/Hw0O/wAAAAAAAAAAAAAAACMNDf9LSkv/c4+y/yEfL/8jQm3/NGWk/yYuR/8rERH/AAAAAAAAAAAAAAAAMxgZ/4GBgv+qu8v/Fw8V/yZEb/80ZaH/Jy5I/wAAAAAAAAAAAAAAAAAAAAAAAAAASUJC/8PIyf8MBwj/J0Bl/yQwSv8rEBH/AAAAAAAAAAAAAAAAAAAAAAAAAAArEBH/Hxoa/wMCAv8KBwj/Ig0O/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKBAT/AAAA/w0EBP8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFAgL/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAwEBP8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADQQE/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAdCwv/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
)


def _scaled_rgba(size: int) -> bytes:
    target_h = max(8, int(size * 0.72))
    target_w = max(4, round(ICON_SOURCE_W * target_h / ICON_SOURCE_H))
    x0 = (size - target_w) // 2
    y0 = (size - target_h) // 2
    out = bytearray(size * size * 4)
    for y in range(target_h):
        sy = min(ICON_SOURCE_H - 1, int(y * ICON_SOURCE_H / target_h))
        for x in range(target_w):
            sx = min(ICON_SOURCE_W - 1, int(x * ICON_SOURCE_W / target_w))
            src_i = (sy * ICON_SOURCE_W + sx) * 4
            dst_i = ((y0 + y) * size + (x0 + x)) * 4
            out[dst_i:dst_i + 4] = ICON_SOURCE_RGBA[src_i:src_i + 4]
    return bytes(out)


def _png_bytes(size: int, rgba: bytes) -> bytes:
    stride = size * 4
    scan = bytearray()
    for y in range(size):
        scan.append(0)
        scan.extend(rgba[y * stride:(y + 1) * stride])

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = binascii.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(scan), 9))
        + chunk(b"IEND", b"")
    )


def build_icon(path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_png_bytes(size, _scaled_rgba(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + (16 * len(images))
    entries = []
    for size, png in zip(sizes, images):
        wh = 0 if size == 256 else size
        entries.append(
            struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(png), offset)
        )
        offset += len(png)
    path.write_bytes(header + b"".join(entries) + b"".join(images))


icon_path = ROOT / "Planilhador.ico"
build_icon(icon_path)

# A janela principal deve usar exatamente o mesmo ícone embutido no EXE.
replace_once(
    '    def build_ui(self):\n',
    '    def build_ui(self):\n'
    '        try:\n'
    '            self.iconbitmap(default=str(app_base_dir() / "Planilhador.ico"))\n'
    '        except Exception:\n'
    '            pass\n',
    "ícone da janela principal",
)

required = [
    'APP_VERSION = "0.4.6"',
    'self.iconbitmap(default=str(app_base_dir() / "Planilhador.ico"))',
    'uniform="launch_top"',
    'text="Lote de trabalho"',
    'text="Leitura / bipagem"',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Build v0.4.6 incompleto: {token}")

if not icon_path.exists() or icon_path.stat().st_size < 1000:
    raise SystemExit("Planilhador.ico não foi gerado corretamente")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.6 gerado — ícone oficial da pena azul")
