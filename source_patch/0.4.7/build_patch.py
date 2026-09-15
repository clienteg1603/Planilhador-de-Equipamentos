from pathlib import Path
import base64
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.6" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.6 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)

source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    if old not in source:
        raise SystemExit(f"Falha ao aplicar patch: {label}")
    source = source.replace(old, new, 1)


source = source.replace('APP_VERSION = "0.4.6"', 'APP_VERSION = "0.4.7"', 1)
if 'APP_VERSION = "0.4.7"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.7")

# ---------------------------------------------------------------------------
# Ícone oficial: usa um ICO Windows real, multirresolução, em vez do gerador
# manual da v0.4.6. Isso evita o Windows/Tk cair no ícone padrão do Python.
# ---------------------------------------------------------------------------
ICON_ICO_B64 = "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"
icon_bytes = base64.b64decode(ICON_ICO_B64)
icon_path = ROOT / "Planilhador.ico"
icon_path.write_bytes(icon_bytes)

if icon_path.stat().st_size != 4638:
    raise SystemExit("Planilhador.ico foi gerado com tamanho inesperado")

# Dá ao aplicativo uma identidade explícita no Windows antes da criação das
# janelas. Isso ajuda a barra de tarefas a usar o ícone do próprio aplicativo,
# em vez de agrupar a janela como Python/Tk.
version_line = 'APP_VERSION = "0.4.7"\n'
app_id_code = '''
if os.name == "nt":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ME.PlanilhadorEquipamentos"
        )
    except Exception:
        pass

'''
replace_once(version_line, version_line + app_id_code, "AppUserModelID do Windows")

# Define o ícone já na criação do Tk principal, antes de login/telas auxiliares.
# iconbitmap(default=...) faz o mesmo ícone ser herdado pelos Toplevels.
pattern = (
    r'(class\s+[A-Za-z_][A-Za-z0-9_]*\s*\(\s*tk\.Tk\s*\)\s*:'
    r'.*?def\s+__init__\s*\([^)]*\)\s*:\s*\n'
    r'\s*super\(\)\.__init__\(\)\s*\n)'
)
early_icon = '''        try:
            self.iconbitmap(default=str(app_base_dir() / "Planilhador.ico"))
        except Exception:
            pass
'''
source, count = re.subn(
    pattern,
    lambda m: m.group(1) + early_icon,
    source,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("Não encontrei a inicialização da janela Tk principal para aplicar o ícone cedo")

# Não abre mais maximizado. Mantém o cálculo de resolução/área útil da v0.4.4,
# mas inicia no tamanho restaurado calculado e centralizado.
replace_once(
    '        self.after(80, self._maximize_initial_window)\n',
    '        self.after(80, self._clamp_window_to_monitor)\n',
    "abertura em modo janela",
)

required = [
    'APP_VERSION = "0.4.7"',
    'SetCurrentProcessExplicitAppUserModelID',
    'self.iconbitmap(default=str(app_base_dir() / "Planilhador.ico"))',
    'self.after(80, self._clamp_window_to_monitor)',
    'uniform="launch_top"',
    'text="Lote de trabalho"',
    'text="Leitura / bipagem"',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Build v0.4.7 incompleto: {token}")

if 'self.after(80, self._maximize_initial_window)' in source:
    raise SystemExit("A chamada de maximização automática ainda está presente")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.7 gerado — ícone corrigido e abertura em modo janela")
