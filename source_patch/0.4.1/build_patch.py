from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.0" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.0 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    if old not in source:
        raise SystemExit(f"Falha ao aplicar patch: {label}")
    source = source.replace(old, new, 1)


source = source.replace('APP_VERSION = "0.4.0"', 'APP_VERSION = "0.4.1"', 1)
if 'APP_VERSION = "0.4.1"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.1")

# Diretório da instalação é diferente do diretório temporário _MEIPASS usado
# pelo PyInstaller onefile. Recursos embutidos continuam em app_base_dir().
needle_base = '''def app_base_dir() -> Path:\n    if getattr(sys, "frozen", False):\n        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))\n    return Path(__file__).resolve().parent\n\n\n'''
replacement_base = '''def app_base_dir() -> Path:\n    if getattr(sys, "frozen", False):\n        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))\n    return Path(__file__).resolve().parent\n\n\ndef install_dir() -> Path:\n    """Pasta persistente onde o programa está instalado."""\n    if getattr(sys, "frozen", False):\n        return Path(sys.executable).resolve().parent\n    return Path(__file__).resolve().parent\n\n\n'''
replace_once(needle_base, replacement_base, "install_dir")

# Limpeza segura da instalação antiga. Remove somente nomes conhecidos do pacote
# Python anterior; nunca toca em DADOS_COMPARTILHADOS nem em pastas desconhecidas.
marker_local = 'def local_config_dir() -> Path:\n'
cleanup = r'''def cleanup_legacy_installation() -> None:
    if not getattr(sys, "frozen", False):
        return
    root = install_dir()
    legacy_files = {
        "Planilhador.pyw",
        "Atualizador.pyw",
        "ABRIR_PROGRAMA.bat",
        "INICIAR.bat",
        "INSTALAR.bat",
        "requirements.txt",
        "update_manifest.json",
        "PUBLICAR_ATUALIZACAO_GITHUB.txt",
        "TESTE_RAPIDO.txt",
        "Planilhador.spec",
        "Atualizador.spec",
    }
    legacy_dirs = {"config", "modelos", "__pycache__", "build", "dist"}

    # A migração automática pode iniciar o EXE por um pequeno Planilhador.pyw.
    # Faz algumas tentativas para dar tempo desse processo encerrar.
    for _ in range(6):
        pending = False
        for name in legacy_files:
            path = root / name
            if not path.exists():
                continue
            try:
                path.unlink()
            except OSError:
                pending = True
        if not pending:
            break
        time.sleep(0.15)

    for name in legacy_dirs:
        path = root / name
        if not path.exists() or not path.is_dir():
            continue
        try:
            shutil.rmtree(path)
        except OSError:
            pass


'''
if marker_local not in source:
    raise SystemExit("local_config_dir não encontrado")
source = source.replace(marker_local, cleanup + marker_local, 1)

# Instalação nova não pode criar dados dentro do _MEIPASS temporário.
replace_once(
    '            shared = str(self.base_dir / "DADOS_COMPARTILHADOS")\n',
    '            shared = str(install_dir() / "DADOS_COMPARTILHADOS")\n',
    "pasta compartilhada persistente",
)

# Limpa restos conhecidos logo no primeiro início da versão EXE.
replace_once(
    '        self.base_dir = app_base_dir()\n        self.equipments = read_json(self.base_dir / "config" / "equipamentos.json", {}) or {}\n',
    '        self.base_dir = app_base_dir()\n        cleanup_legacy_installation()\n        self.equipments = read_json(self.base_dir / "config" / "equipamentos.json", {}) or {}\n',
    "limpeza da instalação antiga",
)

# Atualizador compatível tanto com a instalação Python antiga quanto com o novo EXE.
new_launcher = r'''    def _launch_updater(self, package: Path, new_version: str):
        updates_dir = local_config_dir() / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)

        if getattr(sys, "frozen", False):
            updater = install_dir() / "Atualizador.exe"
            if not updater.exists():
                messagebox.showerror("Atualização", "Atualizador.exe não foi encontrado nesta instalação.")
                return
            temp_updater = updates_dir / f"Atualizador_{int(time.time())}.exe"
            shutil.copy2(updater, temp_updater)
            cmd = [
                str(temp_updater),
                "--pid", str(os.getpid()),
                "--target", str(install_dir()),
                "--package", str(package),
                "--current-version", APP_VERSION,
                "--new-version", new_version,
            ]
        else:
            updater = self.app.base_dir / "Atualizador.pyw"
            if not updater.exists():
                messagebox.showerror("Atualização", "Atualizador.pyw não foi encontrado nesta instalação.")
                return
            temp_updater = updates_dir / f"Atualizador_{int(time.time())}.pyw"
            shutil.copy2(updater, temp_updater)
            cmd = [
                str(Path(sys.executable)), str(temp_updater),
                "--pid", str(os.getpid()),
                "--target", str(install_dir()),
                "--package", str(package),
                "--current-version", APP_VERSION,
                "--new-version", new_version,
            ]

        try:
            kwargs = {"cwd": str(updates_dir), "close_fds": True}
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            messagebox.showerror("Atualização", f"Não consegui iniciar o atualizador:\n{e}")
            return
        self.app.destroy()
'''
sub_once(
    r'    def _launch_updater\(self, package: Path, new_version: str\):.*?(?=\n\nclass LotLock:)',
    new_launcher,
    "launcher do Atualizador.exe",
)

# Mensagem antiga orientava executar INSTALAR.bat, que não existe mais na distribuição.
source = source.replace(
    'O componente pywin32 não está instalado. Execute INSTALAR.bat neste PC.',
    'O componente de integração com o Excel não está disponível nesta instalação. Reinstale a versão EXE do Planilhador.',
)

required = [
    'APP_VERSION = "0.4.1"',
    'def install_dir()',
    'def cleanup_legacy_installation()',
    'Atualizador.exe',
    'shared = str(install_dir() / "DADOS_COMPARTILHADOS")',
    'cleanup_legacy_installation()',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.1 gerado — distribuição EXE")
