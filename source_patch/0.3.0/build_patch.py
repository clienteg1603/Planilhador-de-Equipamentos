from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.2.9" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.2.9 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.2.9"', 'APP_VERSION = "0.3.0"', 1)
if 'APP_VERSION = "0.3.0"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# Etapa 5 — Central: filtros, ordenação, estados visuais e ações contextuais.
# -----------------------------------------------------------------------------
new_build_central = r'''    def _central_status_group(self, info: LotInfo) -> str:
        status = str(info.status or "").upper()
        if "CONFLITO" in status or info.conflict_count or info.post_finalize_changed:
            return "CONFLITO"
        if "REVISÃO" in status or info.sync_review_count:
            return "REVISÃO"
        if info.finalized or status == "FINALIZADO":
            return "FINALIZADO"
        if "ALTERADO" in status or "NOVOS DADOS" in status:
            return "ALTERADO"
        if "EXPORTADO" in status:
            return "EXPORTADO"
        return "ABERTO"

    def _central_sort_value(self, info: LotInfo, column: str):
        if column == "equipamento":
            return str(info.equipment_name or "").casefold()
        if column == "lote":
            return str(info.lot or "").casefold()
        if column == "quantidade":
            return int(info.count or 0)
        if column == "operadora":
            return ", ".join(info.operators).casefold()
        if column == "status":
            order = {"CONFLITO": 0, "REVISÃO": 1, "ALTERADO": 2, "ABERTO": 3, "EXPORTADO": 4, "FINALIZADO": 5}
            return (order.get(self._central_status_group(info), 9), str(info.status or "").casefold())
        return str(info.lot or "").casefold()

    def _central_set_sort(self, column: str):
        if getattr(self, "central_sort_column", None) == column:
            self.central_sort_reverse = not bool(getattr(self, "central_sort_reverse", False))
        else:
            self.central_sort_column = column
            self.central_sort_reverse = False
        self.refresh_lots()

    def _central_update_headings(self):
        if not hasattr(self, "lots_tree"):
            return
        labels = {
            "equipamento": "EQUIPAMENTO",
            "lote": "LOTE",
            "quantidade": "REGISTROS",
            "operadora": "OPERADORA",
            "status": "STATUS",
        }
        active = getattr(self, "central_sort_column", "equipamento")
        reverse = bool(getattr(self, "central_sort_reverse", False))
        for col, label in labels.items():
            arrow = ""
            if col == active:
                arrow = " ▼" if reverse else " ▲"
            self.lots_tree.heading(col, text=label + arrow, command=lambda c=col: self._central_set_sort(c))

    def _central_selected_info_silent(self) -> LotInfo | None:
        if not hasattr(self, "lots_tree"):
            return None
        sel = self.lots_tree.selection()
        if not sel:
            return None
        return getattr(self, "lot_index", {}).get(sel[0])

    def _update_central_action_state(self, *_):
        info = self._central_selected_info_silent()
        buttons = (
            getattr(self, "central_view_btn", None),
            getattr(self, "central_export_btn", None),
            getattr(self, "central_finalize_btn", None),
            getattr(self, "central_conflict_btn", None),
        )
        if not info:
            for btn in buttons:
                if btn:
                    btn.config(state="disabled")
            if hasattr(self, "central_selection_var"):
                self.central_selection_var.set("Selecione um lote para ver as ações disponíveis.")
            return

        issue = bool(info.conflict_count or info.post_finalize_changed or info.sync_review_count)
        can_export = info.count > 0 and not issue
        can_finalize = (
            not info.finalized
            and not issue
            and str(info.status or "").upper() == "EXPORTADO / ABERTO"
        )

        self.central_view_btn.config(state="normal")
        self.central_export_btn.config(state="normal" if can_export else "disabled")
        self.central_finalize_btn.config(state="normal" if can_finalize else "disabled")
        self.central_conflict_btn.config(state="normal" if issue else "disabled")

        group = self._central_status_group(info)
        if issue:
            action_text = "Há pendências: use Conflitos antes de exportar ou finalizar."
        elif info.finalized:
            action_text = "Lote finalizado: consulta e reexportação continuam disponíveis."
        elif can_finalize:
            action_text = "Exportação está atualizada: o lote já pode ser finalizado."
        elif info.count == 0:
            action_text = "Lote vazio: aguarde registros antes de exportar."
        elif group == "ALTERADO":
            action_text = "Os dados mudaram: faça uma nova exportação antes de finalizar."
        else:
            action_text = "Lote aberto: você pode consultar ou exportar o estado atual."
        self.central_selection_var.set(
            f"Selecionado: {info.equipment_name} • Lote {info.lot} • {info.count} registro(s) • {action_text}"
        )

    def build_central_tab(self):
        self.central_sort_column = "equipamento"
        self.central_sort_reverse = False

        title = ttk.Frame(self.tab_central)
        title.pack(fill="x", pady=(0, 8))
        ttk.Label(title, text="Central de lotes", font=("Segoe UI", 15, "bold")).pack(side="left")
        self.central_summary_var = tk.StringVar(value="Carregando lotes...")
        ttk.Label(title, textvariable=self.central_summary_var).pack(side="right")

        filters = ttk.LabelFrame(self.tab_central, text="Pesquisar e filtrar", padding=10)
        filters.pack(fill="x", pady=(0, 8))
        filters.columnconfigure(1, weight=1)

        self.central_search_var = tk.StringVar()
        self.central_equipment_var = tk.StringVar(value="Todos")
        self.central_status_var = tk.StringVar(value="Todos")

        ttk.Label(filters, text="Pesquisar:").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(filters, textvariable=self.central_search_var, width=34)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 16))
        ttk.Label(filters, text="Equipamento:").grid(row=0, column=2, sticky="w")
        self.central_equipment_combo = ttk.Combobox(
            filters, textvariable=self.central_equipment_var, state="readonly", width=22, values=["Todos"]
        )
        self.central_equipment_combo.grid(row=0, column=3, padx=(6, 16))
        ttk.Label(filters, text="Status:").grid(row=0, column=4, sticky="w")
        self.central_status_combo = ttk.Combobox(
            filters,
            textvariable=self.central_status_var,
            state="readonly",
            width=16,
            values=["Todos", "ABERTO", "EXPORTADO", "ALTERADO", "CONFLITO", "REVISÃO", "FINALIZADO"],
        )
        self.central_status_combo.grid(row=0, column=5, padx=(6, 0))
        ttk.Label(
            filters,
            text="A pesquisa procura por equipamento, lote, operadora e status.",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))

        toolbar = ttk.Frame(self.tab_central)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="Atualizar", command=self.refresh_lots).pack(side="left")
        self.central_view_btn = ttk.Button(toolbar, text="Ver lote", command=self.view_selected_lot, state="disabled")
        self.central_view_btn.pack(side="left", padx=(6, 0))
        self.central_export_btn = ttk.Button(toolbar, text="Exportar", command=self.export_selected_lot, state="disabled")
        self.central_export_btn.pack(side="left", padx=(6, 0))
        self.central_finalize_btn = ttk.Button(toolbar, text="Finalizar lote", command=self.finalize_selected_lot, state="disabled")
        self.central_finalize_btn.pack(side="left", padx=(6, 0))
        self.central_conflict_btn = ttk.Button(toolbar, text="Conflitos", command=self.view_selected_conflicts, state="disabled")
        self.central_conflict_btn.pack(side="left", padx=(6, 0))

        self.central_selection_var = tk.StringVar(value="Selecione um lote para ver as ações disponíveis.")
        ttk.Label(self.tab_central, textvariable=self.central_selection_var, wraplength=1000).pack(
            fill="x", pady=(0, 7), anchor="w"
        )

        cols = ("equipamento", "lote", "quantidade", "operadora", "status")
        table_frame = ttk.Frame(self.tab_central)
        table_frame.pack(fill="both", expand=True)
        self.lots_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=21, selectmode="browse")
        widths = {"equipamento":220, "lote":130, "quantidade":100, "operadora":170, "status":300}
        for c in cols:
            self.lots_tree.column(c, width=widths[c], anchor="center", stretch=(c in ("equipamento", "status")))
        self._central_update_headings()

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.lots_tree.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.lots_tree.xview)
        self.lots_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.lots_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.lots_tree.tag_configure("status_aberto", background="#f5f8fb")
        self.lots_tree.tag_configure("status_exportado", background="#eef8ef")
        self.lots_tree.tag_configure("status_alterado", background="#fff7df")
        self.lots_tree.tag_configure("status_conflito", background="#fdecec")
        self.lots_tree.tag_configure("status_revisao", background="#fff1e2")
        self.lots_tree.tag_configure("status_finalizado", background="#eeeeee")

        self.lots_tree.bind("<<TreeviewSelect>>", self._update_central_action_state)
        self.lots_tree.bind("<Double-1>", lambda _e: self.view_selected_lot())
        self.central_search_var.trace_add("write", lambda *_: self.refresh_lots())
        self.central_equipment_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_lots())
        self.central_status_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_lots())
        search_entry.bind("<Escape>", lambda _e: self.central_search_var.set(""))
'''
sub_once(r'    def build_central_tab\(self\):.*?(?=\n    def refresh_lots\()', new_build_central, "build_central_tab")

new_refresh_lots = r'''    def refresh_lots(self):
        if not hasattr(self, "lots_tree"):
            return

        previous = self._central_selected_info_silent()
        previous_key = (previous.equipment_key, previous.lot) if previous else None

        all_infos = self.store.list_lots(self.equipments)
        self._central_all_lots = all_infos

        equipment_names = sorted({x.equipment_name for x in all_infos}, key=str.casefold)
        if hasattr(self, "central_equipment_combo"):
            current_equipment = self.central_equipment_var.get() or "Todos"
            self.central_equipment_combo["values"] = ["Todos", *equipment_names]
            if current_equipment not in ["Todos", *equipment_names]:
                self.central_equipment_var.set("Todos")

        q = self.central_search_var.get().strip().casefold() if hasattr(self, "central_search_var") else ""
        eq_filter = self.central_equipment_var.get().strip() if hasattr(self, "central_equipment_var") else "Todos"
        status_filter = self.central_status_var.get().strip().upper() if hasattr(self, "central_status_var") else "TODOS"

        filtered = []
        for info in all_infos:
            group = self._central_status_group(info)
            if eq_filter and eq_filter != "Todos" and info.equipment_name != eq_filter:
                continue
            if status_filter and status_filter != "TODOS" and group != status_filter:
                continue
            if q:
                haystack = " ".join([
                    str(info.equipment_name or ""),
                    str(info.lot or ""),
                    ", ".join(info.operators),
                    str(info.status or ""),
                    group,
                ]).casefold()
                if q not in haystack:
                    continue
            filtered.append(info)

        sort_col = getattr(self, "central_sort_column", "equipamento")
        reverse = bool(getattr(self, "central_sort_reverse", False))
        filtered.sort(key=lambda x: self._central_sort_value(x, sort_col), reverse=reverse)

        self.lots_tree.delete(*self.lots_tree.get_children())
        self.lot_index = {}
        selected_iid = None
        for idx, info in enumerate(filtered):
            iid = str(idx)
            self.lot_index[iid] = info
            group = self._central_status_group(info)
            tag = {
                "ABERTO": "status_aberto",
                "EXPORTADO": "status_exportado",
                "ALTERADO": "status_alterado",
                "CONFLITO": "status_conflito",
                "REVISÃO": "status_revisao",
                "FINALIZADO": "status_finalizado",
            }.get(group, "status_aberto")
            self.lots_tree.insert("", "end", iid=iid, tags=(tag,), values=(
                info.equipment_name,
                info.lot,
                info.count,
                ", ".join(info.operators) or "—",
                info.status,
            ))
            if previous_key == (info.equipment_key, info.lot):
                selected_iid = iid

        if selected_iid is not None:
            self.lots_tree.selection_set(selected_iid)
            self.lots_tree.focus(selected_iid)
            self.lots_tree.see(selected_iid)

        counts = {k: 0 for k in ("ABERTO", "EXPORTADO", "ALTERADO", "CONFLITO", "REVISÃO", "FINALIZADO")}
        for info in all_infos:
            counts[self._central_status_group(info)] += 1
        self.central_summary_var.set(
            f"Mostrando {len(filtered)} de {len(all_infos)} lotes  •  "
            f"Abertos {counts['ABERTO']}  •  Exportados {counts['EXPORTADO']}  •  "
            f"Alterados {counts['ALTERADO']}  •  Pendências {counts['CONFLITO'] + counts['REVISÃO']}  •  "
            f"Finalizados {counts['FINALIZADO']}"
        )
        self._central_update_headings()
        self._update_central_action_state()
'''
sub_once(r'    def refresh_lots\(self\):.*?(?=\n    def selected_lot_info\()', new_refresh_lots, "refresh_lots")

new_selected = r'''    def selected_lot_info(self) -> LotInfo | None:
        info = self._central_selected_info_silent()
        if not info:
            messagebox.showinfo("Central", "Selecione um lote.")
            return None
        return info
'''
sub_once(r'    def selected_lot_info\(self\) -> LotInfo \| None:.*?(?=\n    def view_selected_lot\()', new_selected, "selected_lot_info")

# -----------------------------------------------------------------------------
# Consulta de lote: filtros adicionais, atualização manual e ordenação das linhas.
# -----------------------------------------------------------------------------
new_view_lot = r'''    def view_selected_lot(self):
        info = self.selected_lot_info()
        if not info:
            return

        win = tk.Toplevel(self)
        win.title(f"{info.equipment_name} — Lote {info.lot}")
        win.geometry("1280x700")
        win.minsize(980, 540)

        records = []
        detail_sort = {"column": "ENVIADO", "reverse": False}

        header_var = tk.StringVar()
        status_var = tk.StringVar()
        summary_var = tk.StringVar()
        count_var = tk.StringVar()
        ttk.Label(win, textvariable=header_var, font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        ttk.Label(win, textvariable=status_var, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(0, 8)
        )

        filters = ttk.LabelFrame(win, text="Filtrar registros", padding=9)
        filters.pack(fill="x", padx=12, pady=(0, 8))
        filters.columnconfigure(5, weight=1)

        user_var = tk.StringVar(value="Todos")
        operator_var = tk.StringVar(value="Todas")
        search_var = tk.StringVar()

        ttk.Label(filters, text="Usuário:").grid(row=0, column=0, sticky="w")
        user_combo = ttk.Combobox(filters, textvariable=user_var, values=["Todos"], state="readonly", width=20)
        user_combo.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(filters, text="Operadora:").grid(row=0, column=2, sticky="w")
        operator_combo = ttk.Combobox(filters, textvariable=operator_var, values=["Todas"], state="readonly", width=15)
        operator_combo.grid(row=0, column=3, padx=(6, 14))
        ttk.Label(filters, text="Pesquisar:").grid(row=0, column=4, sticky="w")
        search_entry = ttk.Entry(filters, textvariable=search_var, width=34)
        search_entry.grid(row=0, column=5, sticky="ew", padx=(6, 10))
        ttk.Button(filters, text="Atualizar dados", command=lambda: load_records(preserve_filters=True)).grid(row=0, column=6)
        ttk.Label(
            filters,
            text="Pesquisa em SERIAL, ICCID, operadora, senha, usuário e PC.",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=7, sticky="w", pady=(6, 0))

        ttk.Label(win, textvariable=summary_var, wraplength=1220).pack(anchor="w", padx=12, pady=(0, 4))
        ttk.Label(win, textvariable=count_var, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(0, 7))

        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA", "USUARIO", "PC", "ENVIADO")
        table_frame = ttk.Frame(win)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        widths = {
            "SERIAL": 145,
            "ICCID": 220,
            "OPERADORA": 105,
            "SENHA": 145,
            "USUARIO": 140,
            "PC": 150,
            "ENVIADO": 180,
        }
        for c in cols:
            tree.column(c, width=widths[c], anchor="center")

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        def detail_value(r, column):
            mapping = {
                "SERIAL": r.get("SERIAL"),
                "ICCID": r.get("ICCID"),
                "OPERADORA": r.get("OPERADORA"),
                "SENHA": r.get("SENHA"),
                "USUARIO": r.get("_usuario"),
                "PC": r.get("_origem_pc"),
                "ENVIADO": r.get("_enviado_em"),
            }
            return str(mapping.get(column) or "").casefold()

        def set_detail_sort(column):
            if detail_sort["column"] == column:
                detail_sort["reverse"] = not detail_sort["reverse"]
            else:
                detail_sort["column"] = column
                detail_sort["reverse"] = False
            refresh_detail_view()

        def update_detail_headings():
            for c in cols:
                arrow = ""
                if c == detail_sort["column"]:
                    arrow = " ▼" if detail_sort["reverse"] else " ▲"
                tree.heading(c, text=c + arrow, command=lambda col=c: set_detail_sort(col))

        def matches_record(r):
            selected_user = user_var.get().strip()
            record_user = str(r.get("_usuario") or "").strip()
            if selected_user and selected_user != "Todos" and record_user != selected_user:
                return False
            selected_operator = operator_var.get().strip()
            if selected_operator and selected_operator != "Todas" and str(r.get("OPERADORA") or "").strip() != selected_operator:
                return False
            q = search_var.get().strip().casefold()
            if not q:
                return True
            haystack = " ".join(str(r.get(k) or "") for k in (
                "SERIAL", "ICCID", "OPERADORA", "SENHA", "_usuario", "_origem_pc", "_enviado_em"
            )).casefold()
            return q in haystack

        def refresh_detail_view(*_):
            tree.delete(*tree.get_children())
            filtered = [r for r in records if matches_record(r)]
            filtered.sort(
                key=lambda r: detail_value(r, detail_sort["column"]),
                reverse=detail_sort["reverse"],
            )
            for r in filtered:
                tree.insert("", "end", values=(
                    r.get("SERIAL") or "—",
                    r.get("ICCID") or "—",
                    r.get("OPERADORA") or "—",
                    r.get("SENHA") or "—",
                    r.get("_usuario") or "—",
                    r.get("_origem_pc") or "—",
                    r.get("_enviado_em") or "—",
                ))
            count_var.set(f"Mostrando {len(filtered)} de {len(records)} registros")
            update_detail_headings()

        def load_records(preserve_filters=False):
            nonlocal records
            old_user = user_var.get()
            old_operator = operator_var.get()
            records = self.store.load_records(info.equipment_key, info.lot)

            users = sorted({str(r.get("_usuario") or "").strip() for r in records if str(r.get("_usuario") or "").strip()}, key=str.casefold)
            operators = sorted({str(r.get("OPERADORA") or "").strip() for r in records if str(r.get("OPERADORA") or "").strip()}, key=str.casefold)
            user_combo["values"] = ["Todos", *users]
            operator_combo["values"] = ["Todas", *operators]
            if preserve_filters and old_user in ["Todos", *users]:
                user_var.set(old_user)
            else:
                user_var.set("Todos")
            if preserve_filters and old_operator in ["Todas", *operators]:
                operator_var.set(old_operator)
            else:
                operator_var.set("Todas")

            user_counts = {}
            for r in records:
                u = str(r.get("_usuario") or "Sem usuário").strip() or "Sem usuário"
                user_counts[u] = user_counts.get(u, 0) + 1
            if user_counts:
                parts = [f"{u}: {user_counts[u]}" for u in sorted(user_counts, key=str.casefold)]
                summary_var.set("Resumo por funcionário — " + "  |  ".join(parts))
            else:
                summary_var.set("Resumo por funcionário — nenhum registro")

            self.refresh_lots()
            current = next((x for x in getattr(self, "_central_all_lots", [])
                            if x.equipment_key == info.equipment_key and x.lot == info.lot), info)
            header_var.set(f"{info.equipment_name} — Lote {info.lot} — {len(records)} registros")
            status_var.set(f"Status atual: {current.status}")
            refresh_detail_view()

        user_combo.bind("<<ComboboxSelected>>", refresh_detail_view)
        operator_combo.bind("<<ComboboxSelected>>", refresh_detail_view)
        search_var.trace_add("write", refresh_detail_view)
        win.bind("<Control-f>", lambda _e: search_entry.focus_set())
        search_entry.bind("<Escape>", lambda _e: search_var.set(""))
        load_records()
        search_entry.focus_set()
'''
sub_once(r'    def view_selected_lot\(self\):.*?(?=\n    def view_selected_conflicts\()', new_view_lot, "view_selected_lot")

# Ações devem ser recalculadas após exportar/finalizar, além do refresh já existente.
# Informação da etapa na tela de Configurações.
needle_info = '        ttk.Label(info, text="Usuários: login por seleção, criação controlada e sequência de bipagem individual por funcionário.").pack(anchor="w", pady=3)\n'
replacement_info = needle_info + '        ttk.Label(info, text="Central: pesquisa, filtros, ordenação, status visuais e ações habilitadas conforme o estado do lote.").pack(anchor="w", pady=3)\n'
if needle_info not in source:
    raise SystemExit("Texto de configuração da v0.2.9 não encontrado")
source = source.replace(needle_info, replacement_info, 1)

required = [
    'APP_VERSION = "0.3.0"',
    'Central de lotes',
    'def _central_status_group',
    'def _central_set_sort',
    'Pesquisar e filtrar',
    'status_conflito',
    'Resumo por funcionário',
    'Atualizar dados',
    'A pesquisa procura por equipamento, lote, operadora e status',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.0 gerado com sucesso")
