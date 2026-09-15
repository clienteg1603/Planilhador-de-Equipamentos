from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.3.3" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.3.3 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar hotfix: {label} (ocorrências={count})")


def replace_once(old: str, new: str, label: str) -> None:
    global source
    if old not in source:
        raise SystemExit(f"Falha ao aplicar hotfix: {label}")
    source = source.replace(old, new, 1)


source = source.replace('APP_VERSION = "0.3.3"', 'APP_VERSION = "0.3.3.1"', 1)
if 'APP_VERSION = "0.3.3.1"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# Hotfix de layout: em telas de ~864 px de altura, a tabela "Peças desta sessão"
# estava ficando sem espaço. O objetivo é preservar a aparência da v0.3.3, mas
# garantir área útil permanente para a tabela.
# -----------------------------------------------------------------------------

# Cabeçalho geral um pouco mais compacto.
replace_once(
    '        self.style.configure("AppTitle.TLabel", font=("Segoe UI", 17, "bold"))\n',
    '        self.style.configure("AppTitle.TLabel", font=("Segoe UI", 15, "bold"))\n',
    "título principal mais compacto",
)
replace_once(
    '        self.style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10))\n',
    '        self.style.configure("TNotebook.Tab", padding=(14, 6), font=("Segoe UI", 10))\n',
    "abas mais compactas",
)
replace_once(
    '        header = ttk.Frame(self, padding=(16, 12, 16, 9))\n',
    '        header = ttk.Frame(self, padding=(16, 8, 16, 6))\n',
    "cabeçalho mais compacto",
)
replace_once(
    '        self.notebook.pack(fill="both", expand=True, padx=14, pady=(10, 14))\n',
    '        self.notebook.pack(fill="both", expand=True, padx=12, pady=(7, 10))\n',
    "margens do notebook",
)
replace_once(
    '        self.tab_scan = ttk.Frame(self.notebook, padding=(16, 14))\n',
    '        self.tab_scan = ttk.Frame(self.notebook, padding=(12, 9))\n',
    "margens do Lançamento",
)

# Compacta os blocos fixos acima da tabela.
replace_once(
    '        selector = ttk.LabelFrame(self.tab_scan, text="Lote de trabalho", padding=12)\n',
    '        selector = ttk.LabelFrame(self.tab_scan, text="Lote de trabalho", padding=(10, 8))\n',
    "seletor de lote compacto",
)
replace_once(
    '        active = ttk.Frame(self.tab_scan, padding=(2, 9, 2, 0))\n',
    '        active = ttk.Frame(self.tab_scan, padding=(2, 5, 2, 0))\n',
    "linha de lote ativo compacta",
)
replace_once(
    '        self.scan_frame = ttk.LabelFrame(self.tab_scan, text="Leitura / bipagem", padding=14)\n',
    '        self.scan_frame = ttk.LabelFrame(self.tab_scan, text="Leitura / bipagem", padding=(12, 9))\n',
    "bloco de bipagem compacto",
)
replace_once(
    '        self.scan_frame.pack(fill="x", pady=(10, 8))\n',
    '        self.scan_frame.pack(fill="x", pady=(6, 6))\n',
    "margens da bipagem",
)
replace_once(
    '            self.scan_frame, textvariable=self.scan_status, style="ScanReady.TLabel", font=("Segoe UI", 14, "bold")\n',
    '            self.scan_frame, textvariable=self.scan_status, style="ScanReady.TLabel", font=("Segoe UI", 13, "bold")\n',
    "status da bipagem compacto",
)
replace_once(
    '        self.scan_status_label.pack(anchor="w", pady=(0, 10))\n',
    '        self.scan_status_label.pack(anchor="w", pady=(0, 7))\n',
    "margem do status",
)
replace_once(
    '        operator_row.pack(fill="x", pady=(10, 0))\n',
    '        operator_row.pack(fill="x", pady=(7, 0))\n',
    "margem da operadora",
)
replace_once(
    '        self.feedback_label.pack(anchor="w", pady=(7, 0))\n',
    '        self.feedback_label.pack(anchor="w", pady=(4, 0))\n',
    "margem do feedback",
)

# Junta Contagem + Última peça em um único quadro. Isso recupera uma faixa
# vertical grande sem perder nenhuma informação.
new_summary = r'''        counters = ttk.LabelFrame(self.tab_scan, text="Resumo do lote", padding=(10, 7))
        counters.pack(fill="x", pady=(0, 6))
        self.user_total_var = tk.StringVar(value=f"{self.username}: —")
        self.lot_total_var = tk.StringVar(value="Total do lote: —")
        self.session_count_var = tk.StringVar(value="Nesta sessão: 0 peças")
        self.sync_status_var = tk.StringVar(value="Atualização automática aguardando lote")
        self.last_piece_var = tk.StringVar(value="Nenhuma peça salva nesta sessão.")
        self.last_piece_detail_var = tk.StringVar(value="")

        for col in range(3):
            counters.columnconfigure(col, weight=1)
        ttk.Label(counters, textvariable=self.user_total_var, style="CountValue.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Label(counters, textvariable=self.lot_total_var, style="CountValue.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 16))
        ttk.Label(counters, textvariable=self.session_count_var, style="CountValue.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Separator(counters, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 5))

        last_row = ttk.Frame(counters)
        last_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Label(last_row, text="Última peça:", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(last_row, textvariable=self.last_piece_var).pack(side="left", padx=(5, 0))
        ttk.Label(last_row, textvariable=self.last_piece_detail_var, style="Muted.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(last_row, textvariable=self.sync_status_var, style="Muted.TLabel").pack(side="right", padx=(12, 0))
'''
sub_once(
    r'        counters = ttk\.LabelFrame\(self\.tab_scan, text="Contagem", padding=10\).*?        ttk\.Label\(last_box, textvariable=self\.last_piece_detail_var\)\.pack\(side="left", padx=\(14, 0\)\)\n',
    new_summary,
    "unificar contagem e última peça",
)

# Junta ações e cabeçalho da tabela na mesma linha. A tabela passa a ser a área
# que realmente cresce com a janela.
new_table_toolbar = r'''        table_header = ttk.Frame(self.tab_scan)
        table_header.pack(fill="x", pady=(0, 5))
        title_group = ttk.Frame(table_header)
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(title_group, text="Peças desta sessão", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            title_group,
            text="  •  salva automaticamente  •  duplo clique para editar",
            style="Muted.TLabel",
        ).pack(side="left")

        ttk.Button(table_header, text="Excluir", command=self.delete_selected_session, style="Danger.TButton").pack(side="right")
        ttk.Button(table_header, text="Editar", command=self.edit_selected_session, style="Quiet.TButton").pack(side="right", padx=(0, 6))
        ttk.Button(table_header, text="Desfazer última", command=self.undo_last_piece, style="Quiet.TButton").pack(side="right", padx=(0, 6))

        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA")
        table_frame = ttk.Frame(self.tab_scan)
        table_frame.pack(fill="both", expand=True)
        self.session_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8, selectmode="extended")
'''
sub_once(
    r'        actions = ttk\.Frame\(self\.tab_scan\).*?        self\.session_tree = ttk\.Treeview\(self\.tab_scan, columns=cols, show="headings", height=12, selectmode="extended"\)\n',
    new_table_toolbar,
    "barra compacta da tabela",
)

# A árvore agora fica em um frame próprio com scrollbar vertical e é sempre a
# região expansível da tela.
replace_once(
    '        self.session_tree.tag_configure("last_saved", background="#e7f4e8")\n        self.session_tree.pack(fill="both", expand=True)\n        self.session_tree.bind("<Double-1>", lambda _e: self.edit_selected_session())\n',
    '        self.session_tree.tag_configure("last_saved", background="#e7f4e8")\n'
    '        scan_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.session_tree.yview)\n'
    '        self.session_tree.configure(yscrollcommand=scan_scroll.set)\n'
    '        self.session_tree.pack(side="left", fill="both", expand=True)\n'
    '        scan_scroll.pack(side="right", fill="y")\n'
    '        self.session_tree.bind("<Double-1>", lambda _e: self.edit_selected_session())\n',
    "tabela expansível com rolagem",
)

required = [
    'APP_VERSION = "0.3.3.1"',
    'text="Resumo do lote"',
    'text="Peças desta sessão"',
    'height=8, selectmode="extended"',
    'scan_scroll = ttk.Scrollbar',
    'text="Desfazer última"',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Hotfix incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.3.1 gerado com sucesso — tabela de sessão preservada em telas baixas")
