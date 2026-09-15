from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
HOTFIX_BUILDER = ROOT / "source_patch" / "0.3.3.1" / "build_patch.py"
if not HOTFIX_BUILDER.exists():
    raise SystemExit("Gerador do hotfix v0.3.3.1 não encontrado")

subprocess.run([sys.executable, str(HOTFIX_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")
source = source.replace('APP_VERSION = "0.3.3.1"', 'APP_VERSION = "0.3.4"', 1)
if 'APP_VERSION = "0.3.4"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.3.4")
source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.4 gerado com sucesso — hotfix de layout aplicado")
