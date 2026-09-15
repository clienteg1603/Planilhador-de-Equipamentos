from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
exe = root / "Planilhador.exe"
if exe.exists():
    kwargs = {"cwd": str(root), "close_fds": True}
    if sys.platform.startswith("win") and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([str(exe)], **kwargs)
