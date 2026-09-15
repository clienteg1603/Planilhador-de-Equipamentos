from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
BROKEN_BUILDER = ROOT / "source_patch" / "0.4.2" / "build_patch.py"
if not BROKEN_BUILDER.exists():
    raise SystemExit("Gerador da v0.4.2 não encontrado")

# A v0.4.2 tinha um replace final excessivamente rígido. Todos os patches
# anteriores eram válidos; somente a inserção após build_ui falhava. Criamos
# uma cópia temporária do gerador com esse ponto corrigido e executamos ela.
text = BROKEN_BUILDER.read_text(encoding="utf-8")
old_block = '''replace_once(\n    '        self.deiconify()\\n        self.build_ui()\\n        if self.settings.get("verificar_atualizacoes_inicio", True):\\n',\n    '        self.deiconify()\\n        self.build_ui()\\n        self.bind("<Configure>", self._schedule_window_clamp, add="+")\\n        self.after(80, self._maximize_initial_window)\\n        if self.settings.get("verificar_atualizacoes_inicio", True):\\n',\n    "maximização e monitoramento responsivo",\n)\n'''
new_block = '''replace_once(\n    '        self.build_ui()\\n',\n    '        self.build_ui()\\n        self.bind("<Configure>", self._schedule_window_clamp, add="+")\\n        self.after(80, self._maximize_initial_window)\\n',\n    "maximização e monitoramento responsivo",\n)\n'''
if old_block not in text:
    raise SystemExit("Bloco problemático da v0.4.2 não encontrado")
text = text.replace(old_block, new_block, 1)

fixed_builder = ROOT / ".build_042_fixed.py"
fixed_builder.write_text(text, encoding="utf-8")
try:
    subprocess.run([sys.executable, str(fixed_builder)], check=True)
finally:
    fixed_builder.unlink(missing_ok=True)

source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")
if 'APP_VERSION = "0.4.2"' not in source:
    raise SystemExit("A base responsiva corrigida não gerou a v0.4.2")
source = source.replace('APP_VERSION = "0.4.2"', 'APP_VERSION = "0.4.4"', 1)

# Evita loop automático de atualização depois de uma tentativa que falhou.
needle_version_check = '''            if version_key(new_version) <= version_key(APP_VERSION):\n                self.app.after(0, lambda: self._up_to_date(manual))\n                return\n\n            assets = data.get("assets") or []\n'''
replacement_version_check = '''            if version_key(new_version) <= version_key(APP_VERSION):\n                self.app.after(0, lambda: self._up_to_date(manual))\n                return\n\n            if not manual:\n                state = read_json(local_config_dir() / "update_state.json", {}) or {}\n                if (\n                    str(state.get("status") or "") == "failed"\n                    and str(state.get("version") or "") == new_version\n                ):\n                    self.app.after(\n                        0,\n                        lambda v=new_version: self.app.set_update_status(\n                            f"A atualização {v} falhou anteriormente. Use Verificar agora para tentar de novo."\n                        ),\n                    )\n                    return\n\n            assets = data.get("assets") or []\n'''
if needle_version_check not in source:
    raise SystemExit("Ponto de verificação de versão não encontrado")
source = source.replace(needle_version_check, replacement_version_check, 1)

needle_launch = '''    def _launch_updater(self, package: Path, new_version: str):\n        updates_dir = local_config_dir() / "updates"\n        updates_dir.mkdir(parents=True, exist_ok=True)\n\n'''
replacement_launch = '''    def _launch_updater(self, package: Path, new_version: str):\n        updates_dir = local_config_dir() / "updates"\n        updates_dir.mkdir(parents=True, exist_ok=True)\n        try:\n            atomic_json_write(\n                local_config_dir() / "update_state.json",\n                {\n                    "status": "attempting",\n                    "version": new_version,\n                    "current_version": APP_VERSION,\n                    "started_at": now_iso(),\n                },\n            )\n        except OSError:\n            pass\n\n'''
if needle_launch not in source:
    raise SystemExit("Launcher do atualizador não encontrado")
source = source.replace(needle_launch, replacement_launch, 1)

required = [
    'APP_VERSION = "0.4.4"',
    'def _monitor_work_area',
    'def _prepare_responsive_window',
    'def _maximize_initial_window',
    'self.settings_canvas = tk.Canvas',
    'self.bind("<Configure>", self._schedule_window_clamp, add="+")',
    'update_state.json',
    '"status": "attempting"',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Build v0.4.4 incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.4 gerado e validado — responsivo + hotfix do atualizador")
