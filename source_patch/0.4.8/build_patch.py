from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.5" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.5 não encontrado")

# A v0.4.5 é a última versão em que o ícone azul padrão do Tk aparecia
# corretamente. Reconstruímos a partir dela e aplicamos apenas a correção da
# abertura em modo janela, sem nenhum override de ícone/AppUserModelID.
subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)

source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")
source = source.replace('APP_VERSION = "0.4.5"', 'APP_VERSION = "0.4.8"', 1)
if 'APP_VERSION = "0.4.8"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.8")

old = '        self.after(80, self._maximize_initial_window)\n'
new = '        self.after(80, self._clamp_window_to_monitor)\n'
if old not in source:
    raise SystemExit("Ponto de maximização automática não encontrado")
source = source.replace(old, new, 1)

# Não aplicar ícone personalizado: o visual aprovado é o feather azul padrão
# do Tk, que o Windows já mostrava corretamente na v0.4.5.
for forbidden in (
    'self.iconbitmap(',
    'SetCurrentProcessExplicitAppUserModelID',
    'Planilhador.ico',
):
    if forbidden in source:
        raise SystemExit(f"Override de ícone indevido encontrado: {forbidden}")

required = [
    'APP_VERSION = "0.4.8"',
    'self.after(80, self._clamp_window_to_monitor)',
    'uniform="launch_top"',
    'text="Lote de trabalho"',
    'text="Leitura / bipagem"',
    'def _monitor_work_area',
    'def _clamp_window_to_monitor',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Build v0.4.8 incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.8 gerado — feather padrão Tk restaurado + abertura em janela")
