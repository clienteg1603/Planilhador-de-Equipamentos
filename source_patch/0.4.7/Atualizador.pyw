from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
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


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_update_state(status: str, version: str, details: str = "") -> None:
    try:
        root = local_root()
        root.mkdir(parents=True, exist_ok=True)
        path = root / "update_state.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(
                {
                    "status": status,
                    "version": str(version or ""),
                    "updated_at": now_text(),
                    "details": str(details or "")[:2000],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temp, path)
    except Exception:
        pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


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
    WAIT_TIMEOUT = 0x00000102
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        time.sleep(0.8)
        return
    try:
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms)
        if result == WAIT_TIMEOUT:
            raise TimeoutError("O Planilhador não encerrou a tempo para aplicar a atualização.")
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


def replace_file_with_retry(src: Path, dst: Path, timeout: float = 25.0) -> None:
    expected = sha256_file(src)
    tmp = dst.with_name(dst.name + ".novo")
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    shutil.copy2(src, tmp)

    deadline = time.time() + timeout
    while True:
        try:
            os.replace(tmp, dst)
            break
        except OSError as exc:
            if time.time() >= deadline:
                raise RuntimeError(
                    f"Não foi possível substituir {dst.name} após várias tentativas. "
                    f"Feche qualquer cópia do Planilhador e tente novamente. Detalhes: {exc}"
                ) from exc
            time.sleep(0.35)

    if not dst.exists():
        raise RuntimeError(f"{dst.name} desapareceu após a atualização.")
    actual = sha256_file(dst)
    if actual != expected:
        raise RuntimeError(f"A conferência de integridade de {dst.name} falhou após a substituição.")


def install_package(target: Path, package: Path, current_version: str) -> tuple[Path, str]:
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

        expected_planilhador = sha256_file(root / "Planilhador.exe")
        try:
            clean_legacy(target)
            replace_file_with_retry(root / "Planilhador.exe", target / "Planilhador.exe")
            replace_file_with_retry(root / "Atualizador.exe", target / "Atualizador.exe")
            readme = root / "LEIA-ME.txt"
            if readme.exists():
                replace_file_with_retry(readme, target / "LEIA-ME.txt", timeout=8.0)
        except Exception:
            restore_backup(target, backup)
            raise

        installed = target / "Planilhador.exe"
        if sha256_file(installed) != expected_planilhador:
            restore_backup(target, backup)
            raise RuntimeError("O Planilhador.exe instalado não corresponde ao arquivo da nova versão.")

    return backup, expected_planilhador


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
        write_update_state("success", args.new_version)
        restart(target)
        return 0
    except Exception as exc:
        write_update_state("failed", args.new_version, str(exc))
        show_error(
            "A atualização não pôde ser concluída. A versão anterior foi preservada sempre que possível.\n\n"
            "O programa não continuará reiniciando automaticamente por causa desta falha.\n\n"
            f"Detalhes: {exc}"
        )
        try:
            restart(target)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
