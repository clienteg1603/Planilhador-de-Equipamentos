from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.2.7" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.2.7 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.2.7"', 'APP_VERSION = "0.2.8"', 1)
if 'APP_VERSION = "0.2.8"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# Estado visual da sessão.
needle_state = '        self._live_refresh_busy = False\n'
replacement_state = (
    '        self._live_refresh_busy = False\n'
    '        self.last_saved_key = None\n'
    '        self._select_last_after_refresh = False\n'
)
if needle_state not in source:
    raise SystemExit("Estado _live_refresh_busy não encontrado")
source = source.replace(needle_state, replacement_state, 1)

# -----------------------------------------------------------------------------
# Tela de lançamento: hierarquia mais clara, contadores destacados e ações rápidas.
# -----------------------------------------------------------------------------
new_build_scan = r'''    def build_scan_tab(self):
        self.style.configure("ScanReady.TLabel", foreground="#1f5f2c")
        self.style.configure("ScanSuccess.TLabel", foreground="#1f6f35", font=("Segoe UI", 10, "bold"))
        self.style.configure("ScanError.TLabel", foreground="#a61b1b", font=("Segoe UI", 10, "bold"))
        self.style.configure("ScanInfo.TLabel", foreground="#4b5563")
        self.style.configure("CountValue.TLabel", font=("Segoe UI", 12, "bold"))
        self.style.configure("ActiveLot.TLabel", font=("Segoe UI", 11, "bold"))

        selector = ttk.LabelFrame(self.tab_scan, text="Lote", padding=12)
        selector.pack(fill="x")
        ttk.Label(selector, text="Equipamento").grid(row=0, column=0, sticky="w")
        self.eq_var = tk.StringVar()
        self.eq_combo = ttk.Combobox(selector, textvariable=self.eq_var, state="readonly", width=28,
                                     values=[cfg["nome"] for cfg in self.equipments.values()])
        self.eq_combo.grid(row=1, column=0, padx=(0, 12), pady=(3, 0), sticky="ew")
        self.eq_combo.bind("<<ComboboxSelected>>", self._on_equipment_changed)

        ttk.Label(selector, text="Lote").grid(row=0, column=1, sticky="w")
        self.lot_var = tk.StringVar()
        self.lot_combo = ttk.Combobox(selector, textvariable=self.lot_var, state="normal", width=20)
        self.lot_combo.grid(row=1, column=1, padx=(0, 12), pady=(3, 0), sticky="ew")
        ttk.Button(selector, text="Iniciar / abrir lote", command=self.start_lot).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(selector, text="Minha sequência", command=self.change_sequence).grid(row=1, column=3)
        selector.columnconfigure(0, weight=1)

        self.open_lots_var = tk.StringVar(value="Selecione um equipamento para ver os lotes abertos.")
        ttk.Label(selector, textvariable=self.open_lots_var, wraplength=900).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        active = ttk.Frame(self.tab_scan, padding=(2, 9, 2, 0))
        active.pack(fill="x")
        self.active_lot_var = tk.StringVar(value="Nenhum lote aberto para bipagem.")
        ttk.Label(active, textvariable=self.active_lot_var, style="ActiveLot.TLabel").pack(anchor="w")

        self.scan_frame = ttk.LabelFrame(self.tab_scan, text="Bipagem", padding=14)
        self.scan_frame.pack(fill="x", pady=(10, 8))
        self.scan_status_label = ttk.Label(
            self.scan_frame, textvariable=self.scan_status, style="ScanReady.TLabel", font=("Segoe UI", 14, "bold")
        )
        self.scan_status_label.pack(anchor="w", pady=(0, 10))
        self.fields_frame = ttk.Frame(self.scan_frame)
        self.fields_frame.pack(fill="x")

        operator_row = ttk.Frame(self.scan_frame)
        operator_row.pack(fill="x", pady=(10, 0))
        ttk.Label(operator_row, text="Operadora:").pack(side="left")
        self.operator_label = ttk.Label(operator_row, textvariable=self.current_operator, font=("Segoe UI", 10, "bold"))
        self.operator_label.pack(side="left", padx=(6, 0))

        self.feedback_var = tk.StringVar(value="Aguardando a primeira peça.")
        self.feedback_label = ttk.Label(self.scan_frame, textvariable=self.feedback_var, style="ScanInfo.TLabel")
        self.feedback_label.pack(anchor="w", pady=(7, 0))

        counters = ttk.LabelFrame(self.tab_scan, text="Contagem", padding=10)
        counters.pack(fill="x", pady=(0, 8))
        self.user_total_var = tk.StringVar(value=f"{self.username}: —")
        self.lot_total_var = tk.StringVar(value="Total do lote: —")
        self.session_count_var = tk.StringVar(value="Nesta sessão: 0 peças")
        self.sync_status_var = tk.StringVar(value="Atualização automática aguardando lote")

        for col in range(3):
            counters.columnconfigure(col, weight=1)
        ttk.Label(counters, textvariable=self.user_total_var, style="CountValue.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 20))
        ttk.Label(counters, textvariable=self.lot_total_var, style="CountValue.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 20))
        ttk.Label(counters, textvariable=self.session_count_var, style="CountValue.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Separator(counters, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        ttk.Label(counters, textvariable=self.sync_status_var).grid(row=2, column=0, columnspan=3, sticky="w")

        last_box = ttk.LabelFrame(self.tab_scan, text="Última peça", padding=(10, 7))
        last_box.pack(fill="x", pady=(0, 8))
        self.last_piece_var = tk.StringVar(value="Nenhuma peça salva nesta sessão.")
        self.last_piece_detail_var = tk.StringVar(value="")
        ttk.Label(last_box, textvariable=self.last_piece_var, font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Label(last_box, textvariable=self.last_piece_detail_var).pack(side="left", padx=(14, 0))

        actions = ttk.Frame(self.tab_scan)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Label(actions, text="Cada peça é salva automaticamente ao concluir os campos.").pack(side="left")
        ttk.Button(actions, text="Excluir selecionada", command=self.delete_selected_session).pack(side="right")
        ttk.Button(actions, text="Editar selecionada", command=self.edit_selected_session).pack(side="right", padx=(0, 8))
        ttk.Button(actions, text="Desfazer última peça", command=self.undo_last_piece).pack(side="right", padx=(0, 8))

        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA")
        self.session_tree = ttk.Treeview(self.tab_scan, columns=cols, show="headings", height=13, selectmode="extended")
        widths = {"SERIAL": 165, "ICCID": 230, "OPERADORA": 130, "SENHA": 165}
        for c in cols:
            self.session_tree.heading(c, text=c)
            self.session_tree.column(c, width=widths[c], anchor="center")
        self.session_tree.tag_configure("last_saved", background="#e7f4e8")
        self.session_tree.pack(fill="both", expand=True)
        self.session_tree.bind("<Double-1>", lambda _e: self.edit_selected_session())
'''
sub_once(r'    def build_scan_tab\(self\):.*?(?=\n    def equipment_key_from_name\()', new_build_scan, "build_scan_tab")

# Feedback visual que não tira foco nem abre janelas para confirmações normais.
marker_prepare = "\n    def prepare_scan_fields(self):\n"
feedback_helper = r'''
    def set_scan_feedback(self, kind: str, text: str):
        if hasattr(self, "feedback_var"):
            self.feedback_var.set(text)
        if hasattr(self, "feedback_label"):
            style = {
                "success": "ScanSuccess.TLabel",
                "error": "ScanError.TLabel",
                "info": "ScanInfo.TLabel",
            }.get(kind, "ScanInfo.TLabel")
            self.feedback_label.configure(style=style)
        if hasattr(self, "scan_status_label"):
            self.scan_status_label.configure(style="ScanError.TLabel" if kind == "error" else "ScanReady.TLabel")

    def update_last_piece_box(self):
        if not hasattr(self, "last_piece_var"):
            return
        if not self.session_records:
            self.last_piece_var.set("Nenhuma peça salva nesta sessão.")
            self.last_piece_detail_var.set("")
            return
        rec = self.session_records[-1]
        self.last_piece_var.set(f"SERIAL {rec.get('SERIAL', '—')}")
        self.last_piece_detail_var.set(
            f"ICCID {rec.get('ICCID', '—')}   •   {rec.get('OPERADORA', '—')}   •   SENHA {rec.get('SENHA', '—')}"
        )
'''
if marker_prepare not in source:
    raise SystemExit("prepare_scan_fields não encontrado")
source = source.replace(marker_prepare, "\n" + feedback_helper + marker_prepare, 1)

new_prepare = r'''    def prepare_scan_fields(self):
        for child in self.fields_frame.winfo_children():
            child.destroy()
        self.scan_entries = {}
        self.scan_sequence = self.get_sequence(self.current_eq_key)
        cfg = self.equipments[self.current_eq_key]
        self.active_lot_var.set(f"{cfg['nome']}  •  Lote {self.current_lot}  •  Usuário: {self.username}")
        self.scan_status.set(f"BIPAR {self.scan_sequence[0]}")
        self.set_scan_feedback("info", "Lote aberto. Bipe os campos na ordem escolhida.")
        for i, field in enumerate(self.scan_sequence):
            frame = ttk.Frame(self.fields_frame)
            frame.grid(row=0, column=i, padx=(0, 12) if i < len(self.scan_sequence) - 1 else 0, sticky="ew")
            self.fields_frame.columnconfigure(i, weight=1)
            ttk.Label(frame, text=f"{i+1}º  {field}", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ent = ttk.Entry(frame, font=("Consolas", 14), width=24)
            ent.pack(fill="x", pady=(4, 0), ipady=3)
            ent.bind("<Return>", lambda e, f=field: self.on_scan_enter(f))
            self.scan_entries[field] = ent
        self.current_operator.set("—")
        first = self.scan_entries[self.scan_sequence[0]]
        self.after(80, first.focus_set)
'''
sub_once(r'    def prepare_scan_fields\(self\):.*?(?=\n    def validate_field\()', new_prepare, "prepare_scan_fields")

new_on_scan = r'''    def on_scan_enter(self, field: str):
        if not self.current_eq_key or not self.current_lot:
            return
        if self.store.is_finalized(self.current_eq_key, self.current_lot):
            self.scan_status.set("LOTE FINALIZADO")
            self.set_scan_feedback("error", "Este lote foi finalizado em outro computador. Não é possível continuar bipando.")
            self.bell()
            return
        ent = self.scan_entries[field]
        ok, value, error = self.validate_field(field, ent.get())
        if not ok:
            self.scan_status.set(f"CONFERIR {field}")
            self.set_scan_feedback("error", error)
            self.bell()
            ent.focus_set()
            ent.selection_range(0, "end")
            return
        ent.delete(0, "end")
        ent.insert(0, value)
        if field == "ICCID":
            self.current_operator.set(self.identify_operator(value) or "—")

        idx = self.scan_sequence.index(field)
        if idx < len(self.scan_sequence) - 1:
            next_field = self.scan_sequence[idx + 1]
            self.scan_status.set(f"BIPAR {next_field}")
            self.set_scan_feedback("info", f"{field} OK. Próximo campo: {next_field}.")
            self.scan_entries[next_field].focus_set()
            return
        self.commit_scanned_record()
'''
sub_once(r'    def on_scan_enter\(self, field: str\):.*?(?=\n    def commit_scanned_record\()', new_on_scan, "on_scan_enter")

new_commit = r'''    def commit_scanned_record(self):
        rec = {}
        for field in self.scan_sequence:
            ok, value, error = self.validate_field(field, self.scan_entries[field].get())
            if not ok:
                self.scan_status.set(f"CONFERIR {field}")
                self.set_scan_feedback("error", error)
                self.scan_entries[field].focus_set()
                self.scan_entries[field].selection_range(0, "end")
                self.bell()
                return
            rec[field] = value
        rec["OPERADORA"] = self.identify_operator(rec["ICCID"])

        for old in self.session_records:
            if old.get("SERIAL") == rec.get("SERIAL"):
                self.scan_status.set("SERIAL DUPLICADA")
                self.set_scan_feedback("error", f"SERIAL {rec['SERIAL']} já foi bipada nesta sessão.")
                self.bell()
                return
            if old.get("ICCID") == rec.get("ICCID"):
                self.scan_status.set("ICCID DUPLICADO")
                self.set_scan_feedback("error", f"ICCID {rec['ICCID']} já foi bipado nesta sessão.")
                self.bell()
                return

        try:
            self.store.submit(
                self.current_eq_key,
                self.equipments[self.current_eq_key]["nome"],
                self.current_lot,
                self.username,
                [rec],
            )
        except (ValueError, TimeoutError, OSError) as exc:
            self.scan_status.set("NÃO FOI SALVO")
            self.set_scan_feedback("error", str(exc))
            self.bell()
            return

        self.session_records.append(rec)
        self.last_saved_key = (str(rec.get("SERIAL") or ""), str(rec.get("ICCID") or ""))
        self._select_last_after_refresh = True
        self.refresh_session_table()
        self.update_last_piece_box()
        for ent in self.scan_entries.values():
            ent.delete(0, "end")
        self.current_operator.set("—")
        self.scan_status.set(f"BIPAR {self.scan_sequence[0]}")
        self.set_scan_feedback("success", f"Peça salva automaticamente ✓  SERIAL {rec.get('SERIAL')}  •  Total da sessão: {len(self.session_records)}")
        self.sync_status_var.set("Peça salva no lote compartilhado ✓")
        self.refresh_live_counts()
        self.scan_entries[self.scan_sequence[0]].focus_set()
'''
sub_once(r'    def commit_scanned_record\(self\):.*?(?=\n    def refresh_session_table\()', new_commit, "commit_scanned_record")

new_refresh = r'''    def refresh_session_table(self):
        if not hasattr(self, "session_tree"):
            return
        self.session_tree.delete(*self.session_tree.get_children())
        last_iid = None
        for i, rec in enumerate(self.session_records):
            key = (str(rec.get("SERIAL") or ""), str(rec.get("ICCID") or ""))
            tags = ("last_saved",) if self.last_saved_key and key == self.last_saved_key else ()
            iid = str(i)
            self.session_tree.insert("", "end", iid=iid, tags=tags, values=(
                rec.get("SERIAL"), rec.get("ICCID"), rec.get("OPERADORA"), rec.get("SENHA")
            ))
            if tags:
                last_iid = iid
        if hasattr(self, "session_count_var"):
            text = f"Nesta sessão: {len(self.session_records)} peças"
            if self.session_count_var.get() != text:
                self.session_count_var.set(text)
        if self._select_last_after_refresh and last_iid is not None:
            self.session_tree.selection_set(last_iid)
            self.session_tree.focus(last_iid)
            self.session_tree.see(last_iid)
        self._select_last_after_refresh = False
'''
sub_once(r'    def refresh_session_table\(self\):.*?(?=\n    def edit_selected_session\()', new_refresh, "refresh_session_table")

# Botão de desfazer: remove com segurança a última peça concluída desta sessão.
marker_delete = "\n    def delete_selected_session(self):\n"
undo_method = r'''
    def undo_last_piece(self):
        if not self.session_records or not self.current_eq_key or not self.current_lot:
            self.set_scan_feedback("info", "Não há peça desta sessão para desfazer.")
            return
        rec = self.session_records[-1]
        if not messagebox.askyesno(
            "Desfazer última peça",
            f"Remover a última peça salva?\n\nSERIAL: {rec.get('SERIAL')}\nICCID: {rec.get('ICCID')}",
        ):
            if self.scan_entries:
                self.scan_entries[self.scan_sequence[0]].focus_set()
            return
        try:
            removed = self.store.delete_record(
                self.current_eq_key,
                self.current_lot,
                self.username,
                rec.get("SERIAL", ""),
                rec.get("ICCID", ""),
            )
        except (ValueError, TimeoutError, OSError) as exc:
            self.set_scan_feedback("error", str(exc))
            self.bell()
            return
        if not removed:
            self.set_scan_feedback("error", "A última peça não foi encontrada no lote compartilhado. Aguarde a sincronização e tente novamente.")
            self.bell()
            return
        self.session_records.pop()
        if self.session_records:
            prev = self.session_records[-1]
            self.last_saved_key = (str(prev.get("SERIAL") or ""), str(prev.get("ICCID") or ""))
        else:
            self.last_saved_key = None
        self.refresh_session_table()
        self.update_last_piece_box()
        self.refresh_live_counts()
        self.scan_status.set(f"BIPAR {self.scan_sequence[0]}")
        self.set_scan_feedback("success", f"Última peça removida ✓  SERIAL {rec.get('SERIAL')}")
        if self.scan_entries:
            self.scan_entries[self.scan_sequence[0]].focus_set()
'''
if marker_delete not in source:
    raise SystemExit("delete_selected_session não encontrado")
source = source.replace(marker_delete, "\n" + undo_method + marker_delete, 1)

new_delete = r'''    def delete_selected_session(self):
        sel = self.session_tree.selection()
        if not sel:
            self.set_scan_feedback("info", "Selecione uma ou mais peças para excluir.")
            return
        if not self.current_eq_key or not self.current_lot:
            return
        quantity = len(sel)
        if not messagebox.askyesno(
            "Excluir peça" if quantity == 1 else "Excluir peças",
            f"Remover {quantity} peça(s) selecionada(s) do lote compartilhado?",
        ):
            if self.scan_entries:
                self.scan_entries[self.scan_sequence[0]].focus_set()
            return
        indexes = sorted([int(x) for x in sel], reverse=True)
        removed_count = 0
        try:
            for idx in indexes:
                if 0 <= idx < len(self.session_records):
                    rec = self.session_records[idx]
                    removed = self.store.delete_record(
                        self.current_eq_key,
                        self.current_lot,
                        self.username,
                        rec.get("SERIAL", ""),
                        rec.get("ICCID", ""),
                    )
                    if not removed:
                        raise ValueError("Não encontrei uma das peças selecionadas no lote compartilhado.")
                    self.session_records.pop(idx)
                    removed_count += 1
        except (ValueError, TimeoutError, OSError) as exc:
            self.set_scan_feedback("error", str(exc))
            self.refresh_live_counts()
            self.bell()
            return

        if self.session_records:
            prev = self.session_records[-1]
            self.last_saved_key = (str(prev.get("SERIAL") or ""), str(prev.get("ICCID") or ""))
        else:
            self.last_saved_key = None
        self.refresh_session_table()
        self.update_last_piece_box()
        self.refresh_live_counts()
        self.scan_status.set(f"BIPAR {self.scan_sequence[0]}")
        self.set_scan_feedback("success", f"{removed_count} peça(s) removida(s) do lote ✓")
        if self.scan_entries:
            self.scan_entries[self.scan_sequence[0]].focus_set()
'''
sub_once(r'    def delete_selected_session\(self\):.*?(?=\n    def send_session\()', new_delete, "delete_selected_session")

# Após editar, atualiza também a caixa da última peça e o destaque da tabela.
old_edit_success = r'''            self.session_records[idx] = corrected
            self.refresh_session_table()
            self.refresh_live_counts()
            self.refresh_lots()
            self.scan_status.set(f"Peça corrigida ✓  —  BIPAR {self.scan_sequence[0]}")
            self.sync_status_var.set("Correção salva no lote compartilhado ✓")'''
new_edit_success = r'''            self.session_records[idx] = corrected
            original_key = (str(original.get("SERIAL") or ""), str(original.get("ICCID") or ""))
            if self.last_saved_key == original_key:
                self.last_saved_key = (str(corrected.get("SERIAL") or ""), str(corrected.get("ICCID") or ""))
            self.refresh_session_table()
            self.update_last_piece_box()
            self.refresh_live_counts()
            self.refresh_lots()
            self.scan_status.set(f"BIPAR {self.scan_sequence[0]}")
            self.set_scan_feedback("success", f"Peça corrigida e salva ✓  SERIAL {corrected.get('SERIAL')}")
            self.sync_status_var.set("Correção salva no lote compartilhado ✓")'''
if old_edit_success not in source:
    raise SystemExit("Sucesso da edição não encontrado")
source = source.replace(old_edit_success, new_edit_success, 1)

# Ao abrir/trocar lote, a caixa da última peça começa limpa.
needle_start = r'''        self.current_eq_key = eq_key
        self.current_lot = lot
        # "Nesta sessão" conta apenas as peças concluídas desde a abertura atual deste lote.
        self.session_records.clear()'''
replacement_start = r'''        self.current_eq_key = eq_key
        self.current_lot = lot
        # "Nesta sessão" conta apenas as peças concluídas desde a abertura atual deste lote.
        self.session_records.clear()
        self.last_saved_key = None'''
if needle_start not in source:
    raise SystemExit("Trecho de abertura do lote não encontrado")
source = source.replace(needle_start, replacement_start, 1)

# Informação na tela de Configurações.
needle_info = '        ttk.Label(info, text="OneDrive: conflitos sincronizados são detectados; exportação/finalização ficam bloqueadas até a revisão.").pack(anchor="w", pady=3)\n'
replacement_info = needle_info + '        ttk.Label(info, text="Bipagem: feedback visual, última peça destacada e ação para desfazer a última peça sem interromper o fluxo.").pack(anchor="w", pady=3)\n'
if needle_info not in source:
    raise SystemExit("Texto de configuração da v0.2.7 não encontrado")
source = source.replace(needle_info, replacement_info, 1)

required = [
    'APP_VERSION = "0.2.8"',
    'Desfazer última peça',
    'def undo_last_piece',
    'def set_scan_feedback',
    'Última peça',
    'last_saved',
    'CountValue.TLabel',
    'Peça salva automaticamente ✓',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.2.8 gerado com sucesso")
