from pathlib import Path
import re

ROOT = Path.cwd()
BASE = ROOT / "source_patch" / "0.2.4"
parts = sorted(BASE.glob("Planilhador.pyw.part*"))
if not parts:
    raise SystemExit("Fonte base 0.2.4 não encontrada")

source = "".join(p.read_text(encoding="utf-8") for p in parts)


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.2.4"', 'APP_VERSION = "0.2.5"', 1)
if 'APP_VERSION = "0.2.5"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# Cada peça passa a ser persistida individualmente. Também é possível remover
# uma peça salva nesta sessão, mantendo o comportamento de correção da tela.
marker = "\n    def meta_path(self, equipment_key: str, lot: str) -> Path:\n"
insert = r'''
    def delete_record(self, equipment_key: str, lot: str, username: str, serial: str, iccid: str) -> bool:
        """Remove um registro exato do próprio usuário, mesmo em pacotes antigos com vários registros."""
        with self.lot_lock(equipment_key, lot):
            if self.is_finalized(equipment_key, lot):
                raise ValueError("Este lote já foi finalizado e não aceita alterações.")
            envios = self.lot_dir(equipment_key, lot) / "envios"
            if not envios.exists():
                return False
            wanted_user = str(username or "").strip().casefold()
            wanted_serial = str(serial or "").strip().upper()
            wanted_iccid = str(iccid or "").strip()
            for path in sorted(envios.glob("*.json"), reverse=True):
                data = read_json(path, {}) or {}
                if str(data.get("usuario") or "").strip().casefold() != wanted_user:
                    continue
                records = list(data.get("registros", []) or [])
                for idx, rec in enumerate(records):
                    if (str(rec.get("SERIAL") or "").strip().upper() == wanted_serial and
                            str(rec.get("ICCID") or "").strip() == wanted_iccid):
                        records.pop(idx)
                        if records:
                            data["registros"] = records
                            data["quantidade"] = len(records)
                            atomic_json_write(path, data)
                        else:
                            path.unlink(missing_ok=True)
                        return True
            return False

    def lot_counts(self, equipment_key: str, lot: str, username: str) -> tuple[int, int]:
        records = self.load_records(equipment_key, lot)
        wanted = str(username or "").strip().casefold()
        user_count = sum(
            1 for r in records
            if str(r.get("_usuario") or "").strip().casefold() == wanted
        )
        return user_count, len(records)
'''
if marker not in source:
    raise SystemExit("Ponto de inserção DataStore não encontrado")
source = source.replace(marker, "\n" + insert + marker, 1)

# Se um lote exportado perder ou ganhar registros, deve aparecer como alterado.
source = source.replace(
    'elif last_exp and last_exp < count:\n                    status = "NOVOS DADOS APÓS EXPORTAÇÃO"',
    'elif last_exp and last_exp != count:\n                    status = "DADOS ALTERADOS APÓS EXPORTAÇÃO"',
    1,
)

# Estado usado pela atualização silenciosa dos contadores.
source = source.replace(
    '        self.scan_status = tk.StringVar(value="Selecione equipamento e lote para começar.")\n',
    '        self.scan_status = tk.StringVar(value="Selecione equipamento e lote para começar.")\n'
    '        self._live_refresh_busy = False\n',
    1,
)

# Inicia o polling depois que a interface existe. Ele apenas altera StringVars,
# nunca reconstrói a tela e por isso não provoca efeito de piscar.
source = source.replace(
    '        self.build_ui()\n        if self.settings.get("verificar_atualizacoes_inicio", True):',
    '        self.build_ui()\n        self.after(1200, self._poll_live_counts)\n        if self.settings.get("verificar_atualizacoes_inicio", True):',
    1,
)

new_build_scan = r'''    def build_scan_tab(self):
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
        # Combobox editável: permite escolher um lote aberto ou digitar um lote novo.
        self.lot_combo = ttk.Combobox(selector, textvariable=self.lot_var, state="normal", width=20)
        self.lot_combo.grid(row=1, column=1, padx=(0, 12), pady=(3, 0), sticky="ew")
        ttk.Button(selector, text="Iniciar / abrir lote", command=self.start_lot).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(selector, text="Minha sequência", command=self.change_sequence).grid(row=1, column=3)
        selector.columnconfigure(0, weight=1)

        self.open_lots_var = tk.StringVar(value="Selecione um equipamento para ver os lotes abertos.")
        ttk.Label(selector, textvariable=self.open_lots_var, wraplength=900).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        self.scan_frame = ttk.LabelFrame(self.tab_scan, text="Bipagem", padding=14)
        self.scan_frame.pack(fill="x", pady=(14, 10))
        ttk.Label(self.scan_frame, textvariable=self.scan_status, font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))
        self.fields_frame = ttk.Frame(self.scan_frame)
        self.fields_frame.pack(fill="x")
        self.operator_label = ttk.Label(self.scan_frame, textvariable=self.current_operator)
        ttk.Label(self.scan_frame, text="Operadora identificada:").pack(anchor="w", pady=(10, 0))
        self.operator_label.pack(anchor="w")

        counters = ttk.LabelFrame(self.tab_scan, text="Contagem do lote", padding=10)
        counters.pack(fill="x", pady=(0, 10))
        self.user_total_var = tk.StringVar(value=f"{self.username}: —")
        self.lot_total_var = tk.StringVar(value="Total do lote: —")
        self.session_count_var = tk.StringVar(value="Nesta sessão: 0")
        self.sync_status_var = tk.StringVar(value="Atualização automática aguardando lote")
        ttk.Label(counters, textvariable=self.user_total_var, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 28))
        ttk.Label(counters, textvariable=self.lot_total_var, font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="w", padx=(0, 28))
        ttk.Label(counters, textvariable=self.session_count_var, font=("Segoe UI", 11, "bold")).grid(row=0, column=2, sticky="w")
        ttk.Label(counters, textvariable=self.sync_status_var).grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

        actions = ttk.Frame(self.tab_scan)
        actions.pack(fill="x", pady=(2, 8))
        ttk.Label(actions, text="Peças concluídas nesta sessão são salvas automaticamente.").pack(side="left")
        ttk.Button(actions, text="Excluir selecionada", command=self.delete_selected_session).pack(side="right")

        cols = ("SERIAL", "ICCID", "OPERADORA", "SENHA")
        self.session_tree = ttk.Treeview(self.tab_scan, columns=cols, show="headings", height=14)
        for c in cols:
            self.session_tree.heading(c, text=c)
            self.session_tree.column(c, width=210 if c == "ICCID" else 150, anchor="center")
        self.session_tree.pack(fill="both", expand=True)
'''
sub_once(r'    def build_scan_tab\(self\):.*?(?=\n    def equipment_key_from_name\()', new_build_scan, "build_scan_tab")

new_equipment_helpers = r'''    def equipment_key_from_name(self, name: str):
        for k, cfg in self.equipments.items():
            if cfg.get("nome") == name:
                return k
        return None

    def _on_equipment_changed(self, *_):
        self.lot_var.set("")
        self.refresh_open_lots_for_equipment()

    def refresh_open_lots_for_equipment(self):
        if not hasattr(self, "lot_combo"):
            return
        eq_key = self.equipment_key_from_name(self.eq_var.get())
        if not eq_key:
            self.lot_combo.configure(values=[])
            self.open_lots_var.set("Selecione um equipamento para ver os lotes abertos.")
            return
        try:
            infos = [
                info for info in self.store.list_lots(self.equipments)
                if info.equipment_key == eq_key and not info.finalized
            ]
        except Exception as exc:
            self.open_lots_var.set(f"Não foi possível ler os lotes agora: {exc}")
            return
        infos.sort(key=lambda x: str(x.lot).casefold())
        self.lot_combo.configure(values=[info.lot for info in infos])
        if infos:
            text = "Lotes abertos: " + "  •  ".join(f"{info.lot} ({info.count} peças)" for info in infos)
        else:
            text = "Nenhum lote aberto para este equipamento. Você pode digitar um lote novo manualmente."
        if self.open_lots_var.get() != text:
            self.open_lots_var.set(text)

    def refresh_live_counts(self):
        if not self.current_eq_key or not self.current_lot or not hasattr(self, "lot_total_var"):
            return
        try:
            user_count, total_count = self.store.lot_counts(self.current_eq_key, self.current_lot, self.username)
        except Exception as exc:
            self.sync_status_var.set(f"Não foi possível atualizar a contagem: {exc}")
            return
        user_text = f"{self.username}: {user_count} peças"
        total_text = f"Total do lote: {total_count} peças"
        session_text = f"Nesta sessão: {len(self.session_records)} peças"
        if self.user_total_var.get() != user_text:
            self.user_total_var.set(user_text)
        if self.lot_total_var.get() != total_text:
            self.lot_total_var.set(total_text)
        if self.session_count_var.get() != session_text:
            self.session_count_var.set(session_text)
        if self.sync_status_var.get() != "Atualização automática ativa — verifica alterações a cada 2 segundos":
            self.sync_status_var.set("Atualização automática ativa — verifica alterações a cada 2 segundos")

    def _poll_live_counts(self):
        if self.current_eq_key and self.current_lot and not self._live_refresh_busy:
            eq_key = self.current_eq_key
            lot = self.current_lot
            username = self.username
            self._live_refresh_busy = True

            def worker():
                error = None
                user_count = total_count = 0
                try:
                    user_count, total_count = self.store.lot_counts(eq_key, lot, username)
                except Exception as exc:
                    error = str(exc)

                def apply_result():
                    self._live_refresh_busy = False
                    if eq_key != self.current_eq_key or lot != self.current_lot:
                        return
                    if error:
                        text = f"Atualização automática: {error}"
                        if self.sync_status_var.get() != text:
                            self.sync_status_var.set(text)
                        return
                    user_text = f"{username}: {user_count} peças"
                    total_text = f"Total do lote: {total_count} peças"
                    if self.user_total_var.get() != user_text:
                        self.user_total_var.set(user_text)
                    if self.lot_total_var.get() != total_text:
                        self.lot_total_var.set(total_text)
                    if self.sync_status_var.get() != "Atualização automática ativa — verifica alterações a cada 2 segundos":
                        self.sync_status_var.set("Atualização automática ativa — verifica alterações a cada 2 segundos")

                try:
                    self.after(0, apply_result)
                except tk.TclError:
                    pass

            threading.Thread(target=worker, daemon=True).start()
        self.after(2000, self._poll_live_counts)
'''
sub_once(r'    def equipment_key_from_name\(self, name: str\):.*?(?=\n    def start_lot\()', new_equipment_helpers, "helpers de lote")

new_start_lot = r'''    def start_lot(self):
        eq_key = self.equipment_key_from_name(self.eq_var.get())
        lot = self.lot_var.get().strip()
        if not eq_key or not lot:
            messagebox.showwarning("Lote", "Selecione o equipamento e informe o lote.")
            return
        if any(ch in lot for ch in "\\/:*?\"<>|"):
            messagebox.showwarning("Lote", "O lote contém caracteres inválidos.")
            return
        if self.store.is_finalized(eq_key, lot):
            messagebox.showerror("Lote finalizado", "Este lote já foi finalizado e não aceita novas peças.")
            self.refresh_open_lots_for_equipment()
            return

        self.current_eq_key = eq_key
        self.current_lot = lot
        # "Nesta sessão" conta apenas as peças concluídas desde a abertura atual deste lote.
        self.session_records.clear()
        self.refresh_session_table()
        self.prepare_scan_fields()
        self.refresh_live_counts()
        self.refresh_open_lots_for_equipment()
'''
sub_once(r'    def start_lot\(self\):.*?(?=\n    def get_sequence\()', new_start_lot, "start_lot")

new_commit = r'''    def commit_scanned_record(self):
        rec = {}
        for field in self.scan_sequence:
            ok, value, error = self.validate_field(field, self.scan_entries[field].get())
            if not ok:
                self.scan_status.set(f"ERRO: {error}")
                self.scan_entries[field].focus_set()
                self.bell()
                return
            rec[field] = value
        rec["OPERADORA"] = self.identify_operator(rec["ICCID"])

        for old in self.session_records:
            if old.get("SERIAL") == rec.get("SERIAL"):
                self.scan_status.set(f"ERRO: SERIAL {rec['SERIAL']} duplicada nesta sessão.")
                self.bell()
                return
            if old.get("ICCID") == rec.get("ICCID"):
                self.scan_status.set(f"ERRO: ICCID {rec['ICCID']} duplicado nesta sessão.")
                self.bell()
                return

        # A peça completa é salva imediatamente. Não existe mais uma fila aguardando "Enviar".
        try:
            self.store.submit(
                self.current_eq_key,
                self.equipments[self.current_eq_key]["nome"],
                self.current_lot,
                self.username,
                [rec],
            )
        except (ValueError, TimeoutError, OSError) as exc:
            self.scan_status.set(f"ERRO AO SALVAR: {exc}")
            self.sync_status_var.set("A peça não foi salva. Corrija ou tente novamente.")
            self.bell()
            return

        self.session_records.append(rec)
        self.refresh_session_table()
        for ent in self.scan_entries.values():
            ent.delete(0, "end")
        self.current_operator.set("—")
        self.scan_status.set(f"Peça salva ✓  —  BIPAR {self.scan_sequence[0]}")
        self.sync_status_var.set("Peça salva no lote compartilhado ✓")
        self.refresh_live_counts()
        self.scan_entries[self.scan_sequence[0]].focus_set()
'''
sub_once(r'    def commit_scanned_record\(self\):.*?(?=\n    def refresh_session_table\()', new_commit, "commit_scanned_record")

new_refresh_session = r'''    def refresh_session_table(self):
        if not hasattr(self, "session_tree"):
            return
        self.session_tree.delete(*self.session_tree.get_children())
        for i, rec in enumerate(self.session_records):
            self.session_tree.insert("", "end", iid=str(i), values=(
                rec.get("SERIAL"), rec.get("ICCID"), rec.get("OPERADORA"), rec.get("SENHA")
            ))
        if hasattr(self, "session_count_var"):
            text = f"Nesta sessão: {len(self.session_records)} peças"
            if self.session_count_var.get() != text:
                self.session_count_var.set(text)
'''
sub_once(r'    def refresh_session_table\(self\):.*?(?=\n    def delete_selected_session\()', new_refresh_session, "refresh_session_table")

new_delete = r'''    def delete_selected_session(self):
        sel = self.session_tree.selection()
        if not sel:
            return
        if not self.current_eq_key or not self.current_lot:
            return
        if not messagebox.askyesno(
            "Excluir peça",
            "A peça selecionada já está salva no lote compartilhado.\n\nDeseja removê-la do lote?",
        ):
            return
        indexes = sorted([int(x) for x in sel], reverse=True)
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
        except (ValueError, TimeoutError, OSError) as exc:
            messagebox.showerror("Não foi possível excluir", str(exc))
            self.refresh_live_counts()
            return
        self.refresh_session_table()
        self.refresh_live_counts()
        self.scan_status.set(f"Peça removida do lote — BIPAR {self.scan_sequence[0]}")
'''
sub_once(r'    def delete_selected_session\(self\):.*?(?=\n    def send_session\()', new_delete, "delete_selected_session")

new_send = r'''    def send_session(self):
        # Mantido apenas por compatibilidade com atalhos de versões antigas.
        messagebox.showinfo(
            "Salvamento automático",
            "Nesta versão cada peça é salva automaticamente assim que a bipagem é concluída.",
        )
'''
sub_once(r'    def send_session\(self\):.*?(?=\n    # ---------------- Central ----------------)', new_send, "send_session")

# A mensagem antiga dizia que havia peças esperando envio; agora elas já estão salvas.
source = source.replace(
    'messagebox.showwarning("Pasta compartilhada", "Envie ou exclua as peças da sessão antes de trocar a pasta compartilhada.")',
    'messagebox.showwarning("Pasta compartilhada", "Há peças desta sessão já salvas no lote atual. Reinicie o programa antes de trocar a pasta compartilhada.")',
    1,
)

# Verificações de sanidade do resultado.
required = [
    'APP_VERSION = "0.2.5"',
    'def refresh_open_lots_for_equipment',
    'def _poll_live_counts',
    'def delete_record',
    'Peça salva no lote compartilhado',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

(ROOT / "Planilhador.pyw").write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.2.5 gerado com sucesso")
