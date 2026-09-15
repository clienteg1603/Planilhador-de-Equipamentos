from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.3.2" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.3.2 não encontrado")

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


source = source.replace('APP_VERSION = "0.3.2"', 'APP_VERSION = "0.3.3"', 1)
if 'APP_VERSION = "0.3.3"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# Etapa 8 — polimento visual geral, sem mudar regras de negócio.
# -----------------------------------------------------------------------------
new_build_ui = r'''    def build_ui(self):
        # Linguagem visual comum às três áreas do programa. Mantém o tema nativo
        # do Windows e melhora hierarquia, espaçamento e leitura sem adicionar
        # dependências gráficas externas.
        self.style.configure("TButton", padding=(10, 6))
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 7))
        self.style.configure("Quiet.TButton", padding=(10, 6))
        self.style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 6))
        self.style.configure("AppTitle.TLabel", font=("Segoe UI", 17, "bold"))
        self.style.configure("PageTitle.TLabel", font=("Segoe UI", 15, "bold"))
        self.style.configure("SectionTitle.TLabel", font=("Segoe UI", 11, "bold"))
        self.style.configure("Muted.TLabel", foreground="#5f6368")
        self.style.configure("Meta.TLabel", font=("Segoe UI", 9, "bold"), foreground="#4b5563")
        self.style.configure("TLabelframe", padding=4)
        self.style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        self.style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10))
        self.style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        header = ttk.Frame(self, padding=(16, 12, 16, 9))
        header.pack(fill="x")
        brand = ttk.Frame(header)
        brand.pack(side="left", fill="x", expand=True)
        ttk.Label(brand, text=APP_NAME, style="AppTitle.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text=f"Bipagem, conferência e exportação compartilhada  •  versão {APP_VERSION}",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        account = ttk.Frame(header)
        account.pack(side="right", padx=(18, 0))
        ttk.Label(account, text=f"Usuário: {self.username}", style="Meta.TLabel").pack(anchor="e")
        ttk.Label(account, text="Dados compartilhados ativos", style="Muted.TLabel").pack(anchor="e", pady=(2, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=14)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        self.tab_scan = ttk.Frame(self.notebook, padding=(16, 14))
        self.tab_central = ttk.Frame(self.notebook, padding=(16, 14))
        self.tab_settings = ttk.Frame(self.notebook, padding=(16, 14))
        self.notebook.add(self.tab_scan, text="Lançamento")
        self.notebook.add(self.tab_central, text="Central")
        self.notebook.add(self.tab_settings, text="Configurações")

        self.build_scan_tab()
        self.build_central_tab()
        self.build_settings_tab()
        self.refresh_lots()
'''
sub_once(r'    def build_ui\(self\):.*?(?=\n    # ---------------- Lançamento ----------------)', new_build_ui, "cabeçalho e estilos gerais")

# Lançamento: ações principais mais fáceis de distinguir e seções com nomes mais claros.
replace_once(
    '        selector = ttk.LabelFrame(self.tab_scan, text="Lote", padding=12)\n',
    '        selector = ttk.LabelFrame(self.tab_scan, text="Lote de trabalho", padding=12)\n',
    "título do seletor de lote",
)
replace_once(
    '        ttk.Button(selector, text="Iniciar / abrir lote", command=self.start_lot).grid(row=1, column=2, padx=(0, 8))\n',
    '        ttk.Button(selector, text="Abrir lote", command=self.start_lot, style="Primary.TButton").grid(row=1, column=2, padx=(0, 8))\n',
    "botão abrir lote",
)
replace_once(
    '        ttk.Button(selector, text="Minha sequência", command=self.change_sequence).grid(row=1, column=3)\n',
    '        ttk.Button(selector, text="Minha sequência", command=self.change_sequence, style="Quiet.TButton").grid(row=1, column=3)\n',
    "botão sequência",
)
replace_once(
    '        self.scan_frame = ttk.LabelFrame(self.tab_scan, text="Bipagem", padding=14)\n',
    '        self.scan_frame = ttk.LabelFrame(self.tab_scan, text="Leitura / bipagem", padding=14)\n',
    "título da bipagem",
)
replace_once(
    '        ttk.Button(actions, text="Excluir selecionada", command=self.delete_selected_session).pack(side="right")\n'
    '        ttk.Button(actions, text="Editar selecionada", command=self.edit_selected_session).pack(side="right", padx=(0, 8))\n'
    '        ttk.Button(actions, text="Desfazer última peça", command=self.undo_last_piece).pack(side="right", padx=(0, 8))\n',
    '        ttk.Button(actions, text="Excluir selecionada", command=self.delete_selected_session, style="Danger.TButton").pack(side="right")\n'
    '        ttk.Button(actions, text="Editar selecionada", command=self.edit_selected_session, style="Quiet.TButton").pack(side="right", padx=(0, 8))\n'
    '        ttk.Button(actions, text="Desfazer última peça", command=self.undo_last_piece, style="Quiet.TButton").pack(side="right", padx=(0, 8))\n',
    "ações de bipagem",
)

# Introduz um pequeno cabeçalho sobre a tabela sem mexer na lógica/seleção.
needle_table = '        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA")\n        self.session_tree = ttk.Treeview(self.tab_scan, columns=cols, show="headings", height=13, selectmode="extended")\n'
replacement_table = r'''        table_header = ttk.Frame(self.tab_scan)
        table_header.pack(fill="x", pady=(2, 6))
        ttk.Label(table_header, text="Peças desta sessão", style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(
            table_header,
            text="Duplo clique em uma linha para editar.",
            style="Muted.TLabel",
        ).pack(side="right")

        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA")
        self.session_tree = ttk.Treeview(self.tab_scan, columns=cols, show="headings", height=12, selectmode="extended")
'''
replace_once(needle_table, replacement_table, "cabeçalho da tabela de sessão")

# Central: título, resumo e botões com pesos visuais consistentes.
replace_once(
    '        ttk.Label(title, text="Central de lotes", font=("Segoe UI", 15, "bold")).pack(side="left")\n',
    '        ttk.Label(title, text="Central de lotes", style="PageTitle.TLabel").pack(side="left")\n',
    "título da Central",
)
replace_once(
    '        ttk.Label(title, textvariable=self.central_summary_var).pack(side="right")\n',
    '        ttk.Label(title, textvariable=self.central_summary_var, style="Muted.TLabel").pack(side="right")\n',
    "resumo da Central",
)
replace_once(
    '        ttk.Button(toolbar, text="Atualizar", command=self.refresh_lots).pack(side="left")\n',
    '        ttk.Button(toolbar, text="Atualizar", command=self.refresh_lots, style="Quiet.TButton").pack(side="left")\n',
    "botão atualizar Central",
)
replace_once(
    '        self.central_view_btn = ttk.Button(toolbar, text="Ver lote", command=self.view_selected_lot, state="disabled")\n',
    '        self.central_view_btn = ttk.Button(toolbar, text="Ver lote", command=self.view_selected_lot, state="disabled", style="Primary.TButton")\n',
    "botão ver lote",
)
replace_once(
    '        self.central_export_btn = ttk.Button(toolbar, text="Exportar", command=self.export_selected_lot, state="disabled")\n',
    '        self.central_export_btn = ttk.Button(toolbar, text="Exportar", command=self.export_selected_lot, state="disabled", style="Primary.TButton")\n',
    "botão exportar",
)
replace_once(
    '        self.central_finalize_btn = ttk.Button(toolbar, text="Finalizar lote", command=self.finalize_selected_lot, state="disabled")\n',
    '        self.central_finalize_btn = ttk.Button(toolbar, text="Finalizar lote", command=self.finalize_selected_lot, state="disabled", style="Primary.TButton")\n',
    "botão finalizar",
)
replace_once(
    '        self.central_conflict_btn = ttk.Button(toolbar, text="Conflitos", command=self.view_selected_conflicts, state="disabled")\n',
    '        self.central_conflict_btn = ttk.Button(toolbar, text="Conflitos", command=self.view_selected_conflicts, state="disabled", style="Danger.TButton")\n',
    "botão conflitos",
)
replace_once(
    '        self.central_open_export_btn = ttk.Button(toolbar, text="Abrir última pasta", command=self.open_last_export_folder, state="disabled")\n',
    '        self.central_open_export_btn = ttk.Button(toolbar, text="Abrir última pasta", command=self.open_last_export_folder, state="disabled", style="Quiet.TButton")\n',
    "botão abrir última pasta",
)
replace_once(
    '        ttk.Label(self.tab_central, textvariable=self.central_selection_var, wraplength=1000).pack(\n',
    '        ttk.Label(self.tab_central, textvariable=self.central_selection_var, wraplength=1000, style="Muted.TLabel").pack(\n',
    "linha contextual da Central",
)

# Configurações: adiciona um cabeçalho de página e um texto curto de orientação.
settings_header = r'''    def build_settings_tab(self):
        heading = ttk.Frame(self.tab_settings)
        heading.pack(fill="x", pady=(0, 10))
        ttk.Label(heading, text="Configurações", style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            heading,
            text="Ajuste compartilhamento, atualizações e cadastros sem interferir nos lotes já gravados.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        box = ttk.LabelFrame(self.tab_settings, text="Pasta compartilhada", padding=14)
'''
sub_once(
    r'    def build_settings_tab\(self\):\n        box = ttk.LabelFrame\(self\.tab_settings, text="Pasta compartilhada", padding=14\)\n',
    settings_header,
    "cabeçalho das Configurações",
)

# Cadastros: pequenas melhorias de leitura na janela administrativa.
replace_once(
    '        ttk.Label(win, text="Equipamentos, operadoras e modelos", font=("Segoe UI", 15, "bold")).pack(\n',
    '        ttk.Label(win, text="Equipamentos, operadoras e modelos", style="PageTitle.TLabel").pack(\n',
    "título do gerenciador",
)
replace_once(
    '        ttk.Button(top, text="Novo equipamento", command=lambda: new_equipment()).pack(side="left")\n',
    '        ttk.Button(top, text="Novo equipamento", command=lambda: new_equipment(), style="Primary.TButton").pack(side="left")\n',
    "novo equipamento",
)
replace_once(
    '        ttk.Button(bottom, text="Salvar equipamento", command=lambda: save_equipment()).pack(side="right", padx=(0, 8))\n',
    '        ttk.Button(bottom, text="Salvar equipamento", command=lambda: save_equipment(), style="Primary.TButton").pack(side="right", padx=(0, 8))\n',
    "salvar equipamento",
)

# Texto da tela de configurações para registrar a etapa visual sem poluir a interface.
needle_info = '        ttk.Label(info, text="Usuários: login por seleção, criação controlada e sequência de bipagem individual por funcionário.").pack(anchor="w", pady=3)\n'
if needle_info in source:
    source = source.replace(
        needle_info,
        needle_info + '        ttk.Label(info, text="Interface: hierarquia visual, espaçamento e ações padronizadas na v0.3.3.").pack(anchor="w", pady=3)\n',
        1,
    )

required = [
    'APP_VERSION = "0.3.3"',
    'Primary.TButton',
    'AppTitle.TLabel',
    'PageTitle.TLabel',
    'Peças desta sessão',
    'Leitura / bipagem',
    'Ajuste compartilhamento, atualizações e cadastros',
    'Dados compartilhados ativos',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.3 gerado com sucesso")
