from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
original = ROOT / "source_patch" / "0.2.8" / "build_patch.py"
text = original.read_text(encoding="utf-8")

pattern = re.compile(
    r'# Ao abrir/trocar lote, a caixa da última peça começa limpa\.\n'
    r'needle_start = r\'\'\'.*?'
    r'source = source\.replace\(needle_start, replacement_start, 1\)\n',
    re.S,
)

replacement = '''# Ao abrir/trocar lote, a caixa da última peça começa limpa.\nsource, start_count = re.subn(\n    r'(        self\\.current_eq_key = eq_key\\n        self\\.current_lot = lot\\n(?:        #.*\\n)?        self\\.session_records\\.clear\\(\\)\\n)',\n    lambda m: m.group(1) + '        self.last_saved_key = None\\n',\n    source,\n    count=1,\n)\nif start_count != 1:\n    raise SystemExit(f"Trecho de abertura do lote não encontrado (ocorrências={start_count})")\n'''

text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"Bloco antigo de abertura do lote não encontrado no gerador (ocorrências={count})")

temp = ROOT / "source_patch" / "0.2.8" / "_build_patch_fixed.py"
temp.write_text(text, encoding="utf-8")
try:
    subprocess.run([sys.executable, str(temp)], check=True)
finally:
    try:
        temp.unlink()
    except OSError:
        pass
