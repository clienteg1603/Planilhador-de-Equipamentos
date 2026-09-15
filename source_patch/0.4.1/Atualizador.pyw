from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

APP_NAME = "Planilhador de Equipamentos"

LEGACY_FILES = {
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
LEGACY_DIRS = {"config", "modelos", "__pycache__", "build", "dist"}


def local_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "PlanilhadorEquipamentos"
    return Path.home() / ".planilhador_equipamentos"


def show_error(text: str) -> None:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Atualização do Planilhador", text, parent=root)
    root.destroy()


def wait_for_pid(pid: int, timeout_ms: int = 45000) -> None:
    if pid <= 0 or os.name != "nt":
        time.sleep(1.5)
        return
    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def find_package_root(extracted: Path) -> Path:
    direct = extracted / "Planilhador.exe"
    if direct.exists():
        return extracted
    matches = list(extracted.rglob("Planilhador.exe"))
    if not matches:
        raise RuntimeError("O pacote não contém Planilhador.exe.")
    return matches[0].parent


def backup_installation(target: Path, current_version: str) -> Path:
    backup_dir = local_root() / "versoes"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"Instalacao_{current_version or 'anterior'}_{stamp}.zip"
    with zipfile.ZipFile(backup, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        names = {"Planilhador.exe", "Atualizador.exe", "LEIA-ME.txt", *LEGACY_FILES}
        for name in sorted(names):
            path = target / name
            if path.is_file():
                zf.write(path, path.name)
        for dirname in sorted(LEGACY_DIRS):
            folder = target / dirname
            if not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if path.is_file():
                    try:
                        zf.write(path, path.relative_to(target).as_posix())
                    except OSError:
                        pass
    return backup


def clean_legacy(target: Path) -> None:
    for name in LEGACY_FILES:
        try:
            (target / name).unlink(missing_ok=True)
        except OSError:
            pass
    for name in LEGACY_DIRS:
        path = target / name
        if path.is_dir():
            try:
                shutil.rmtree(path)
            except OSError:
                pass


def restore_backup(target: Path, backup: Path) -> None:
    try:
        with zipfile.ZipFile(backup, "r") as zf:
            zf.extractall(target)
    except Exception:
        pass


def install_package(target: Path, package: Path, current_version: str) -> None:
    if not package.exists():
        raise FileNotFoundError(f"Pacote não encontrado: {package}")
    target.mkdir(parents=True, exist_ok=True)
    backup = backup_installation(target, current_version)

    with tempfile.TemporaryDirectory(prefix="PlanilhadorUpdate_") as temp:
        extracted = Path(temp)
        with zipfile.ZipFile(package, "r") as zf:
            zf.extractall(extracted)
        root = find_package_root(extracted)

        required = [root / "Planilhador.exe", root / "Atualizador.exe"]
        missing = [p.name for p in required if not p.exists()]
        if missing:
            raise RuntimeError("Pacote incompleto: " + ", ".join(missing))

        try:
            clean_legacy(target)
            for name in ("Planilhador.exe", "Atualizador.exe", "LEIA-ME.txt"):
                src = root / name
                if not src.exists():
                    continue
                tmp = target / (name + ".novo")
                shutil.copy2(src, tmp)
                os.replace(tmp, target / name)
        except Exception:
            restore_backup(target, backup)
            raise


def restart(target: Path) -> None:
    exe = target / "Planilhador.exe"
    if not exe.exists():
        raise RuntimeError("Planilhador.exe não foi encontrado após a atualização.")
    kwargs = {"cwd": str(target), "close_fds": True}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([str(exe)], **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--target", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--current-version", default="")
    parser.add_argument("--new-version", default="")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    package = Path(args.package).resolve()
    try:
        wait_for_pid(args.pid)
        install_package(target, package, args.current_version)
        restart(target)
        return 0
    except Exception as exc:
        show_error(
            "A atualização não pôde ser concluída. A versão anterior foi preservada sempre que possível.\n\n"
            f"Detalhes: {exc}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
