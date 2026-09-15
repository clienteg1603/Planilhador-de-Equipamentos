from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.2" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.2 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    if old not in source:
        raise SystemExit(f"Falha ao aplicar patch: {label}")
    source = source.replace(old, new, 1)


source = source.replace('APP_VERSION = "0.4.2"', 'APP_VERSION = "0.4.3"', 1)
if 'APP_VERSION = "0.4.3"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.3")

# Evita que uma atualização que falhou seja oferecida automaticamente em todo
# início do programa. O usuário ainda pode tentar novamente manualmente em
# Configurações > Verificar agora.
needle_version_check = '''            if version_key(new_version) <= version_key(APP_VERSION):\n                self.app.after(0, lambda: self._up_to_date(manual))\n                return\n\n            assets = data.get("assets") or []\n'''
replacement_version_check = '''            if version_key(new_version) <= version_key(APP_VERSION):\n                self.app.after(0, lambda: self._up_to_date(manual))\n                return\n\n            if not manual:\n                state = read_json(local_config_dir() / "update_state.json", {}) or {}\n                if (\n                    str(state.get("status") or "") == "failed"\n                    and str(state.get("version") or "") == new_version\n                ):\n                    self.app.after(\n                        0,\n                        lambda v=new_version: self.app.set_update_status(\n                            f"A atualização {v} falhou anteriormente. Use Verificar agora para tentar de novo."\n                        ),\n                    )\n                    return\n\n            assets = data.get("assets") or []\n'''
replace_once(needle_version_check, replacement_version_check, "bloqueio de loop automático")

# Registra a tentativa antes de encerrar o programa. O Atualizador.exe troca o
# estado para success/failed. Isso também ajuda a diagnosticar o que aconteceu.
needle_launch = '''    def _launch_updater(self, package: Path, new_version: str):\n        updates_dir = local_config_dir() / "updates"\n        updates_dir.mkdir(parents=True, exist_ok=True)\n\n'''
replacement_launch = '''    def _launch_updater(self, package: Path, new_version: str):\n        updates_dir = local_config_dir() / "updates"\n        updates_dir.mkdir(parents=True, exist_ok=True)\n        try:\n            atomic_json_write(\n                local_config_dir() / "update_state.json",\n                {\n                    "status": "attempting",\n                    "version": new_version,\n                    "current_version": APP_VERSION,\n                    "started_at": now_iso(),\n                },\n            )\n        except OSError:\n            pass\n\n'''
replace_once(needle_launch, replacement_launch, "registro de tentativa de atualização")

required = [
    'APP_VERSION = "0.4.3"',
    'update_state.json',
    'A atualização {v} falhou anteriormente',
    '"status": "attempting"',
    'def _monitor_work_area',
    'self.settings_canvas = tk.Canvas',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.3 gerado — hotfix de atualização")
