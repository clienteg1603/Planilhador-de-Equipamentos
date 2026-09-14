from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
original = ROOT / "source_patch" / "0.2.8" / "build_patch.py"
text = original.read_text(encoding="utf-8")

old = r'''# Ao abrir/trocar lote, a caixa da última peça começa limpa.
needle_start = r'''        self.current_eq_key = eq_key
        self.current_lot = lot
        # "Nesta sessão" conta apenas as peças concluídas desde a abertura atual deste lote.
        self.session_records.clear()'''
replacement_start = r'''        self.current_eq_key = eq_key
        self.current_lot = lot
        # "Nesta sessão" conta apenas as peças concluídas desde a abertura atual deste lote.
        self.session_records.clear()
        self.last_saved_key = None'''
if needle_start not in source:
    raise SystemExit("Trecho de abertura do lote não encontrado")
source = source.replace(needle_start, replacement_start, 1)
'''

new = r'''# Ao abrir/trocar lote, a caixa da última peça começa limpa.
source, start_count = re.subn(
    r'(        self\.current_eq_key = eq_key\n        self\.current_lot = lot\n(?:        #.*\n)?        self\.session_records\.clear\(\)\n)',
    lambda m: m.group(1) + '        self.last_saved_key = None\n',
    source,
    count=1,
)
if start_count != 1:
    raise SystemExit(f"Trecho de abertura do lote não encontrado (ocorrências={start_count})")
'''

if old not in text:
    raise SystemExit("Bloco antigo de abertura do lote não encontrado no gerador")
text = text.replace(old, new, 1)

temp = ROOT / "source_patch" / "0.2.8" / "_build_patch_fixed.py"
temp.write_text(text, encoding="utf-8")
try:
    subprocess.run([sys.executable, str(temp)], check=True)
finally:
    try:
        temp.unlink()
    except OSError:
        pass
