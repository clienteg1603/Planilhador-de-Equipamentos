from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.4.4" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.4.4 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.4.4"', 'APP_VERSION = "0.4.5"', 1)
if 'APP_VERSION = "0.4.5"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.5")

# Lançamento: Lote de trabalho e Leitura/bipagem passam a dividir a mesma linha.
# Isso reduz a altura fixa do topo e entrega mais área vertical ao resumo e à tabela.
new_build_scan = r'''    def build_scan_tab(self):
        self.style.configure("ScanReady.TLabel", foreground="#1f5f2c")
        self.style.configure("ScanSuccess.TLabel", foreground="#1f6f35", font=("Segoe UI", 10, "bold"))
        self.style.configure("ScanError.TLabel", foreground="#a61b1b", font=("Segoe UI", 10, "bold"))
        self.style.configure("ScanInfo.TLabel", foreground="#4b5563")
        self.style.configure("CountValue.TLabel", font=("Segoe UI", 12, "bold"))
        self.style.configure("ActiveLot.TLabel", font=("Segoe UI", 10, "bold"))

        top = ttk.Frame(self.tab_scan)
        top.pack(fill="x", pady=(0, 6))
        top.columnconfigure(0, weight=1, uniform="launch_top")
        top.columnconfigure(1, weight=1, uniform="launch_top")

        selector = ttk.LabelFrame(top, text="Lote de trabalho", padding=(10, 8))
        selector.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        selector.columnconfigure(0, weight=3)
        selector.columnconfigure(1, weight=2)

        ttk.Label(selector, text="Equipamento").grid(row=0, column=0, sticky="w")
        ttk.Label(selector, text="Lote").grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.eq_var = tk.StringVar()
        self.eq_combo = ttk.Combobox(
            selector,
            textvariable=self.eq_var,
            state="readonly",
            values=[cfg["nome"] for cfg in self.equipments.values()],
        )
        self.eq_combo.grid(row=1, column=0, padx=(0, 8), pady=(3, 0), sticky="ew")
        self.eq_combo.bind("<<ComboboxSelected>>", self._on_equipment_changed)

        self.lot_var = tk.StringVar()
        self.lot_combo = ttk.Combobox(selector, textvariable=self.lot_var, state="normal")
        self.lot_combo.grid(row=1, column=1, padx=(8, 0), pady=(3, 0), sticky="ew")

        selector_actions = ttk.Frame(selector)
        selector_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        ttk.Button(
            selector_actions,
            text="Abrir lote",
            command=self.start_lot,
            style="Primary.TButton",
        ).pack(side="left")
        ttk.Button(
            selector_actions,
            text="Minha sequência",
            command=self.change_sequence,
            style="Quiet.TButton",
        ).pack(side="left", padx=(7, 0))

        self.open_lots_var = tk.StringVar(value="Selecione um equipamento para ver os lotes abertos.")
        ttk.Label(selector, textvariable=self.open_lots_var, wraplength=650).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        self.active_lot_var = tk.StringVar(value="Nenhum lote aberto para bipagem.")
        ttk.Label(
            selector,
            textvariable=self.active_lot_var,
            style="ActiveLot.TLabel",
            wraplength=650,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))

        self.scan_frame = ttk.LabelFrame(top, text="Leitura / bipagem", padding=(10, 8))
        self.scan_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        scan_head = ttk.Frame(self.scan_frame)
        scan_head.pack(fill="x")
        self.scan_status_label = ttk.Label(
            scan_head,
            textvariable=self.scan_status,
            style="ScanReady.TLabel",
            font=("Segoe UI", 13, "bold"),
        )
        self.scan_status_label.pack(side="left")

        operator_head = ttk.Frame(scan_head)
        operator_head.pack(side="right", padx=(12, 0))
        ttk.Label(operator_head, text="Operadora:").pack(side="left")
        self.operator_label = ttk.Label(
            operator_head,
            textvariable=self.current_operator,
            font=("Segoe UI", 10, "bold"),
        )
        self.operator_label.pack(side="left", padx=(5, 0))

        self.fields_frame = ttk.Frame(self.scan_frame)
        self.fields_frame.pack(fill="x", pady=(7, 0))

        self.feedback_var = tk.StringVar(value="Aguardando a primeira peça.")
        self.feedback_label = ttk.Label(
            self.scan_frame,
            textvariable=self.feedback_var,
            style="ScanInfo.TLabel",
            wraplength=700,
        )
        self.feedback_label.pack(anchor="w", pady=(5, 0))

        counters = ttk.LabelFrame(self.tab_scan, text="Resumo do lote", padding=(10, 7))
        counters.pack(fill="x", pady=(0, 6))
        self.user_total_var = tk.StringVar(value=f"{self.username}: —")
        self.lot_total_var = tk.StringVar(value="Total do lote: —")
        self.session_count_var = tk.StringVar(value="Nesta sessão: 0 peças")
        self.sync_status_var = tk.StringVar(value="Atualização automática aguardando lote")
        self.last_piece_var = tk.StringVar(value="Nenhuma peça salva nesta sessão.")
        self.last_piece_detail_var = tk.StringVar(value="")

        for col in range(3):
            counters.columnconfigure(col, weight=1)
        ttk.Label(counters, textvariable=self.user_total_var, style="CountValue.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Label(counters, textvariable=self.lot_total_var, style="CountValue.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 16)
        )
        ttk.Label(counters, textvariable=self.session_count_var, style="CountValue.TLabel").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Separator(counters, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(6, 5)
        )

        last_row = ttk.Frame(counters)
        last_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Label(last_row, text="Última peça:", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(last_row, textvariable=self.last_piece_var).pack(side="left", padx=(5, 0))
        ttk.Label(last_row, textvariable=self.last_piece_detail_var, style="Muted.TLabel").pack(
            side="left", padx=(10, 0)
        )
        ttk.Label(last_row, textvariable=self.sync_status_var, style="Muted.TLabel").pack(
            side="right", padx=(12, 0)
        )

        table_header = ttk.Frame(self.tab_scan)
        table_header.pack(fill="x", pady=(0, 5))
        title_group = ttk.Frame(table_header)
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(title_group, text="Peças desta sessão", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            title_group,
            text="  •  salva automaticamente  •  duplo clique para editar",
            style="Muted.TLabel",
        ).pack(side="left")

        ttk.Button(
            table_header,
            text="Excluir",
            command=self.delete_selected_session,
            style="Danger.TButton",
        ).pack(side="right")
        ttk.Button(
            table_header,
            text="Editar",
            command=self.edit_selected_session,
            style="Quiet.TButton",
        ).pack(side="right", padx=(0, 6))
        ttk.Button(
            table_header,
            text="Desfazer última",
            command=self.undo_last_piece,
            style="Quiet.TButton",
        ).pack(side="right", padx=(0, 6))

        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA")
        table_frame = ttk.Frame(self.tab_scan)
        table_frame.pack(fill="both", expand=True)
        self.session_tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            height=8,
            selectmode="extended",
        )
        widths = {"SERIAL": 165, "ICCID": 230, "OPERADORA": 130, "SENHA": 165}
        for c in cols:
            self.session_tree.heading(c, text=c)
            self.session_tree.column(c, width=widths[c], anchor="center")
        self.session_tree.tag_configure("last_saved", background="#e7f4e8")
        scan_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.session_tree.yview)
        self.session_tree.configure(yscrollcommand=scan_scroll.set)
        self.session_tree.pack(side="left", fill="both", expand=True)
        scan_scroll.pack(side="right", fill="y")
        self.session_tree.bind("<Double-1>", lambda _e: self.edit_selected_session())
'''
sub_once(
    r'    def build_scan_tab\(self\):.*?(?=\n    def equipment_key_from_name\()',
    new_build_scan,
    "layout horizontal do Lançamento",
)

# Os campos continuam lado a lado, mas um pouco mais estreitos para caber bem
# na metade direita também em modo janela.
source = source.replace('font=("Consolas", 14), width=24', 'font=("Consolas", 14), width=18', 1)
source = source.replace('padx=(0, 12) if i < len(self.scan_sequence) - 1 else 0', 'padx=(0, 8) if i < len(self.scan_sequence) - 1 else 0', 1)

required = [
    'APP_VERSION = "0.4.5"',
    'uniform="launch_top"',
    'text="Lote de trabalho"',
    'text="Leitura / bipagem"',
    'text="Resumo do lote"',
    'text="Peças desta sessão"',
    'width=18',
    'scan_scroll = ttk.Scrollbar',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Build v0.4.5 incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.5 gerado — Lote e Bipagem lado a lado")
