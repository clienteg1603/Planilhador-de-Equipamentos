from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.1" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.1 não encontrado")

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


source = source.replace('APP_VERSION = "0.4.1"', 'APP_VERSION = "0.4.2"', 1)
if 'APP_VERSION = "0.4.2"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.2")

# A API de monitor do Windows permite usar a área útil real do monitor onde a
# janela está (descontando barra de tarefas). Em outros sistemas há fallback Tk.
if "import ctypes\n" not in source:
    replace_once("import json\n", "import ctypes\nimport json\n", "import ctypes")

# Tira o tamanho fixo antigo. O tamanho restaurado passa a ser calculado pela
# resolução/área útil do monitor e a janela inicia maximizada.
replace_once(
    '        self.geometry("1060x700")\n        self.minsize(900, 620)\n',
    '        self._resize_after_id = None\n        self._prepare_responsive_window()\n',
    "geometria responsiva inicial",
)

# Métodos de janela dentro de App, antes de build_ui.
marker_build_ui = "    def build_ui(self):\n"
responsive_methods = r'''    # ---------------- Janela responsiva ----------------
    def _monitor_work_area(self) -> tuple[int, int, int, int]:
        """Retorna left, top, right, bottom da área útil do monitor atual."""
        if os.name == "nt":
            try:
                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", ctypes.c_ulong),
                        ("rcMonitor", RECT),
                        ("rcWork", RECT),
                        ("dwFlags", ctypes.c_ulong),
                    ]

                user32 = ctypes.windll.user32
                user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                user32.MonitorFromWindow.restype = ctypes.c_void_p
                user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
                user32.GetMonitorInfoW.restype = ctypes.c_int

                self.update_idletasks()
                monitor = user32.MonitorFromWindow(ctypes.c_void_p(self.winfo_id()), 2)
                if monitor:
                    info = MONITORINFO()
                    info.cbSize = ctypes.sizeof(MONITORINFO)
                    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                        work = info.rcWork
                        if work.right > work.left and work.bottom > work.top:
                            return int(work.left), int(work.top), int(work.right), int(work.bottom)
            except Exception:
                pass

        width = max(640, int(self.winfo_screenwidth() or 1024))
        height = max(480, int(self.winfo_screenheight() or 768))
        return 0, 0, width, height

    def _update_dynamic_minsize(self, area: tuple[int, int, int, int] | None = None):
        left, top, right, bottom = area or self._monitor_work_area()
        work_w = max(640, right - left)
        work_h = max(480, bottom - top)
        # Nunca força uma janela maior do que a área disponível. Em monitores
        # pequenos a interface continua utilizável graças às áreas expansíveis/
        # roláveis; em monitores grandes mantém um mínimo confortável.
        min_w = min(820, max(640, int(work_w * 0.64)))
        min_h = min(560, max(480, int(work_h * 0.64)))
        self.minsize(min_w, min_h)

    def _prepare_responsive_window(self):
        left, top, right, bottom = self._monitor_work_area()
        work_w = max(640, right - left)
        work_h = max(480, bottom - top)
        self._update_dynamic_minsize((left, top, right, bottom))

        # Este é o tamanho usado ao clicar em Restaurar. Fica sempre menor que
        # a área útil do monitor e centralizado, sem passar por baixo da taskbar.
        width = min(1180, max(760, int(work_w * 0.90)))
        height = min(820, max(560, int(work_h * 0.86)))
        width = min(width, max(640, work_w - 24))
        height = min(height, max(480, work_h - 24))
        x = left + max(8, (work_w - width) // 2)
        y = top + max(8, (work_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _maximize_initial_window(self):
        try:
            if os.name == "nt":
                self.state("zoomed")
            else:
                self.attributes("-zoomed", True)
        except (tk.TclError, AttributeError):
            # Se o gerenciador de janelas não suportar maximização, o tamanho
            # restaurado já foi calculado para caber no monitor.
            pass

    def _schedule_window_clamp(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.after(180, self._clamp_window_to_monitor)

    def _clamp_window_to_monitor(self):
        self._resize_after_id = None
        try:
            if self.state() != "normal":
                return
        except tk.TclError:
            return

        left, top, right, bottom = self._monitor_work_area()
        self._update_dynamic_minsize((left, top, right, bottom))
        margin = 8
        max_w = max(640, (right - left) - margin * 2)
        max_h = max(480, (bottom - top) - margin * 2)

        width = min(max(self.winfo_width(), 1), max_w)
        height = min(max(self.winfo_height(), 1), max_h)
        x = self.winfo_x()
        y = self.winfo_y()
        x = max(left + margin, min(x, right - width - margin))
        y = max(top + margin, min(y, bottom - height - margin))

        current = (self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y())
        wanted = (width, height, x, y)
        if current != wanted:
            self.geometry(f"{width}x{height}+{x}+{y}")

'''
if marker_build_ui not in source:
    raise SystemExit("build_ui não encontrado")
source = source.replace(marker_build_ui, responsive_methods + marker_build_ui, 1)

# Configurações ganhou conteúdo suficiente para estourar telas baixas. Em vez de
# reduzir tudo, torna somente essa aba verticalmente rolável.
old_tabs = '''        self.tab_scan = ttk.Frame(self.notebook, padding=(12, 9))\n        self.tab_central = ttk.Frame(self.notebook, padding=(16, 14))\n        self.tab_settings = ttk.Frame(self.notebook, padding=(16, 14))\n        self.notebook.add(self.tab_scan, text="Lançamento")\n        self.notebook.add(self.tab_central, text="Central")\n        self.notebook.add(self.tab_settings, text="Configurações")\n\n        self.build_scan_tab()\n        self.build_central_tab()\n        self.build_settings_tab()\n        self.refresh_lots()\n'''
new_tabs = r'''        self.tab_scan = ttk.Frame(self.notebook, padding=(12, 9))
        self.tab_central = ttk.Frame(self.notebook, padding=(16, 14))
        self.settings_host = ttk.Frame(self.notebook)
        settings_bg = self.style.lookup("TFrame", "background") or self.cget("background")
        self.settings_canvas = tk.Canvas(
            self.settings_host,
            highlightthickness=0,
            borderwidth=0,
            background=settings_bg,
        )
        self.settings_scroll = ttk.Scrollbar(
            self.settings_host,
            orient="vertical",
            command=self.settings_canvas.yview,
        )
        self.settings_canvas.configure(yscrollcommand=self.settings_scroll.set)
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        self.settings_scroll.pack(side="right", fill="y")
        self.tab_settings = ttk.Frame(self.settings_canvas, padding=(16, 14))
        self._settings_canvas_window = self.settings_canvas.create_window(
            (0, 0), window=self.tab_settings, anchor="nw"
        )

        def sync_settings_scrollregion(_event=None):
            bbox = self.settings_canvas.bbox("all")
            if bbox:
                self.settings_canvas.configure(scrollregion=bbox)

        def sync_settings_width(event):
            self.settings_canvas.itemconfigure(self._settings_canvas_window, width=max(1, event.width))

        self.tab_settings.bind("<Configure>", sync_settings_scrollregion)
        self.settings_canvas.bind("<Configure>", sync_settings_width)

        self.notebook.add(self.tab_scan, text="Lançamento")
        self.notebook.add(self.tab_central, text="Central")
        self.notebook.add(self.settings_host, text="Configurações")

        self.build_scan_tab()
        self.build_central_tab()
        self.build_settings_tab()
        self.refresh_lots()
        sync_settings_scrollregion()
'''
replace_once(old_tabs, new_tabs, "Configurações roláveis")

# Depois do login e da montagem da interface, maximiza. Quando o usuário clicar
# em Restaurar, o geometry calculado anteriormente é usado. O clamp acompanha
# mudança para outro monitor sem ficar redimensionando a janela continuamente.
replace_once(
    '        self.deiconify()\n        self.build_ui()\n        if self.settings.get("verificar_atualizacoes_inicio", True):\n',
    '        self.deiconify()\n        self.build_ui()\n        self.bind("<Configure>", self._schedule_window_clamp, add="+")\n        self.after(80, self._maximize_initial_window)\n        if self.settings.get("verificar_atualizacoes_inicio", True):\n',
    "maximização e monitoramento responsivo",
)

required = [
    'APP_VERSION = "0.4.2"',
    'import ctypes',
    'def _monitor_work_area',
    'def _prepare_responsive_window',
    'def _maximize_initial_window',
    'def _clamp_window_to_monitor',
    'self.settings_canvas = tk.Canvas',
    'self.notebook.add(self.settings_host, text="Configurações")',
    'self.bind("<Configure>", self._schedule_window_clamp, add="+")',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.2 gerado — janela responsiva e maximização segura")
