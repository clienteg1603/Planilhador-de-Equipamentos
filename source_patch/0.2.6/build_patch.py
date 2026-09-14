from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.2.5" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.2.5 não encontrado")

# Reconstrói primeiro exatamente a v0.2.5 já publicada e aplica somente as mudanças desta etapa.
subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.2.5"', 'APP_VERSION = "0.2.6"', 1)
if 'APP_VERSION = "0.2.6"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# DataStore: edição atômica da peça, histórico e proteção pós-exportação.
# -----------------------------------------------------------------------------
marker = "\n    def lot_counts(self, equipment_key: str, lot: str, username: str) -> tuple[int, int]:\n"
insert = r'''
    def edit_record(self, equipment_key: str, lot: str, username: str,
                    old_serial: str, old_iccid: str, new_record: dict) -> bool:
        """Edita uma peça do próprio usuário e registra a correção no histórico do lote."""
        with self.lot_lock(equipment_key, lot):
            if self.is_finalized(equipment_key, lot):
                raise ValueError("Este lote já foi finalizado e não aceita alterações.")

            envios = self.lot_dir(equipment_key, lot) / "envios"
            if not envios.exists():
                return False

            wanted_user = str(username or "").strip().casefold()
            wanted_serial = str(old_serial or "").strip().upper()
            wanted_iccid = str(old_iccid or "").strip()
            target_path = None
            target_index = None
            target_data = None
            old_record = None

            for path in sorted(envios.glob("*.json"), reverse=True):
                data = read_json(path, {}) or {}
                if str(data.get("usuario") or "").strip().casefold() != wanted_user:
                    continue
                records = list(data.get("registros", []) or [])
                for idx, rec in enumerate(records):
                    if (str(rec.get("SERIAL") or "").strip().upper() == wanted_serial and
                            str(rec.get("ICCID") or "").strip() == wanted_iccid):
                        target_path = path
                        target_index = idx
                        target_data = data
                        old_record = dict(rec)
                        break
                if target_path is not None:
                    break

            if target_path is None or target_data is None or target_index is None or old_record is None:
                return False

            # Verifica duplicidades contra todo o lote, excluindo somente a peça que está sendo editada.
            existing = []
            skipped_target = False
            for rec in self.load_records(equipment_key, lot):
                is_target = (
                    not skipped_target and
                    str(rec.get("_usuario") or "").strip().casefold() == wanted_user and
                    str(rec.get("SERIAL") or "").strip().upper() == wanted_serial and
                    str(rec.get("ICCID") or "").strip() == wanted_iccid
                )
                if is_target:
                    skipped_target = True
                    continue
                existing.append(rec)

            clean_new = {
                "SERIAL": str(new_record.get("SERIAL") or ""),
                "ICCID": str(new_record.get("ICCID") or ""),
                "OPERADORA": str(new_record.get("OPERADORA") or ""),
                "SENHA": str(new_record.get("SENHA") or ""),
            }
            dup = self.duplicate_messages(existing, [clean_new])
            if dup:
                raise ValueError("\n".join(dup))

            records = list(target_data.get("registros", []) or [])
            records[target_index] = clean_new
            target_data["registros"] = records
            target_data["quantidade"] = len(records)
            target_data["ultima_correcao_em"] = now_iso()
            atomic_json_write(target_path, target_data)

            history_dir = self.lot_dir(equipment_key, lot) / "historico"
            history_dir.mkdir(parents=True, exist_ok=True)
            history_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_edicao_" + uuid.uuid4().hex[:8] + ".json"
            atomic_json_write(history_dir / history_name, {
                "tipo": "EDICAO",
                "editado_em": now_iso(),
                "usuario": username,
                "antes": old_record,
                "depois": clean_new,
            })

            meta = self.load_meta(equipment_key, lot)
            if int(meta.get("ultima_exportacao_quantidade", 0) or 0) > 0:
                meta["dados_alterados_apos_exportacao"] = True
                meta["ultima_alteracao_em"] = now_iso()
                atomic_json_write(self.meta_path(equipment_key, lot), meta)
            return True
'''
if marker not in source:
    raise SystemExit("Ponto de inserção edit_record não encontrado")
source = source.replace(marker, "\n" + insert + marker, 1)

# Exclusão também deve invalidar uma exportação anterior de forma explícita.
old_delete_tail = r'''                        if records:
                            data["registros"] = records
                            data["quantidade"] = len(records)
                            atomic_json_write(path, data)
                        else:
                            path.unlink(missing_ok=True)
                        return True'''
new_delete_tail = r'''                        if records:
                            data["registros"] = records
                            data["quantidade"] = len(records)
                            atomic_json_write(path, data)
                        else:
                            path.unlink(missing_ok=True)
                        meta = self.load_meta(equipment_key, lot)
                        if int(meta.get("ultima_exportacao_quantidade", 0) or 0) > 0:
                            meta["dados_alterados_apos_exportacao"] = True
                            meta["ultima_alteracao_em"] = now_iso()
                            atomic_json_write(self.meta_path(equipment_key, lot), meta)
                        return True'''
if old_delete_tail not in source:
    raise SystemExit("Trecho final de delete_record não encontrado")
source = source.replace(old_delete_tail, new_delete_tail, 1)

# Uma nova exportação passa a representar novamente o estado atual do lote.
old_mark = r'''        meta.update({
            "ultima_exportacao_em": now_iso(),
            "ultima_exportacao_quantidade": count,
            "arquivos": files,
        })'''
new_mark = r'''        meta.update({
            "ultima_exportacao_em": now_iso(),
            "ultima_exportacao_quantidade": count,
            "arquivos": files,
            "dados_alterados_apos_exportacao": False,
        })'''
if old_mark not in source:
    raise SystemExit("mark_exported não encontrado")
source = source.replace(old_mark, new_mark, 1)

# Editar sem mudar a quantidade também precisa mudar o estado do lote.
old_status = r'''                if finalized:
                    status = "FINALIZADO"
                elif last_exp and last_exp == count:
                    status = "EXPORTADO / ABERTO"
                elif last_exp and last_exp != count:
                    status = "DADOS ALTERADOS APÓS EXPORTAÇÃO"
                else:
                    status = "ABERTO"'''
new_status = r'''                if finalized:
                    status = "FINALIZADO"
                elif bool(meta.get("dados_alterados_apos_exportacao")):
                    status = "DADOS ALTERADOS APÓS EXPORTAÇÃO"
                elif last_exp and last_exp == count:
                    status = "EXPORTADO / ABERTO"
                elif last_exp and last_exp != count:
                    status = "DADOS ALTERADOS APÓS EXPORTAÇÃO"
                else:
                    status = "ABERTO"'''
if old_status not in source:
    raise SystemExit("Bloco de status do lote não encontrado")
source = source.replace(old_status, new_status, 1)

# Finalização não pode ocorrer após edição mesmo quando a quantidade permaneceu igual.
old_finalize_check = r'''            if int(meta.get("ultima_exportacao_quantidade", -1)) != count:
                raise ValueError(
                    "O lote mudou desde a última exportação (ou ainda não foi exportado). "
                    "Exporte novamente antes de finalizar."
                )'''
new_finalize_check = r'''            if (int(meta.get("ultima_exportacao_quantidade", -1)) != count or
                    bool(meta.get("dados_alterados_apos_exportacao"))):
                raise ValueError(
                    "O lote mudou desde a última exportação (ou ainda não foi exportado). "
                    "Exporte novamente antes de finalizar."
                )'''
if old_finalize_check not in source:
    raise SystemExit("Validação de finalização não encontrada")
source = source.replace(old_finalize_check, new_finalize_check, 1)

# -----------------------------------------------------------------------------
# Interface: botão Editar + duplo clique + janela de correção segura.
# -----------------------------------------------------------------------------
old_actions = r'''        actions = ttk.Frame(self.tab_scan)
        actions.pack(fill="x", pady=(2, 8))
        ttk.Label(actions, text="Peças concluídas nesta sessão são salvas automaticamente.").pack(side="left")
        ttk.Button(actions, text="Excluir selecionada", command=self.delete_selected_session).pack(side="right")'''
new_actions = r'''        actions = ttk.Frame(self.tab_scan)
        actions.pack(fill="x", pady=(2, 8))
        ttk.Label(actions, text="Peças concluídas nesta sessão são salvas automaticamente.").pack(side="left")
        ttk.Button(actions, text="Excluir selecionada", command=self.delete_selected_session).pack(side="right")
        ttk.Button(actions, text="Editar selecionada", command=self.edit_selected_session).pack(side="right", padx=(0, 8))'''
if old_actions not in source:
    raise SystemExit("Barra de ações da bipagem não encontrada")
source = source.replace(old_actions, new_actions, 1)

old_tree_pack = '        self.session_tree.pack(fill="both", expand=True)\n'
new_tree_pack = '        self.session_tree.pack(fill="both", expand=True)\n        self.session_tree.bind("<Double-1>", lambda _e: self.edit_selected_session())\n'
if old_tree_pack not in source:
    raise SystemExit("Treeview da sessão não encontrado")
source = source.replace(old_tree_pack, new_tree_pack, 1)

marker_delete = "\n    def delete_selected_session(self):\n"
edit_method = r'''
    def edit_selected_session(self):
        sel = self.session_tree.selection()
        if not sel:
            messagebox.showinfo("Editar peça", "Selecione uma peça da sessão para editar.")
            return
        if len(sel) != 1:
            messagebox.showinfo("Editar peça", "Selecione somente uma peça por vez.")
            return
        if not self.current_eq_key or not self.current_lot:
            return
        if self.store.is_finalized(self.current_eq_key, self.current_lot):
            messagebox.showerror("Lote finalizado", "Este lote já foi finalizado e não aceita alterações.")
            return

        idx = int(sel[0])
        if idx < 0 or idx >= len(self.session_records):
            return
        original = dict(self.session_records[idx])

        win = tk.Toplevel(self)
        win.title("Editar peça")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Corrigir peça bipada", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, padx=18, pady=(18, 12), sticky="w"
        )

        vars_by_field = {
            "SERIAL": tk.StringVar(value=str(original.get("SERIAL") or "")),
            "ICCID": tk.StringVar(value=str(original.get("ICCID") or "")),
            "SENHA": tk.StringVar(value=str(original.get("SENHA") or "")),
        }
        edit_entries = {}
        row = 1
        for field in ("SERIAL", "ICCID", "SENHA"):
            ttk.Label(win, text=field).grid(row=row, column=0, padx=(18, 10), pady=6, sticky="e")
            ent = ttk.Entry(win, textvariable=vars_by_field[field], width=32, font=("Consolas", 11))
            ent.grid(row=row, column=1, padx=(0, 18), pady=6, sticky="w")
            edit_entries[field] = ent
            row += 1

        operator_var = tk.StringVar(value=str(original.get("OPERADORA") or "—"))
        ttk.Label(win, text="OPERADORA").grid(row=row, column=0, padx=(18, 10), pady=6, sticky="e")
        ttk.Label(win, textvariable=operator_var, font=("Segoe UI", 10, "bold")).grid(
            row=row, column=1, padx=(0, 18), pady=6, sticky="w"
        )
        row += 1

        info_var = tk.StringVar(value="A operadora é recalculada automaticamente pelo ICCID.")
        ttk.Label(win, textvariable=info_var, wraplength=410).grid(
            row=row, column=0, columnspan=2, padx=18, pady=(6, 10), sticky="w"
        )
        row += 1

        def update_operator(*_):
            iccid = vars_by_field["ICCID"].get().strip()
            operator_var.set(self.identify_operator(iccid) or "—")

        vars_by_field["ICCID"].trace_add("write", update_operator)

        def cancel():
            win.destroy()
            if self.scan_entries:
                self.after(50, self.scan_entries[self.scan_sequence[0]].focus_set)

        def save_edit():
            corrected = {}
            for field in ("SERIAL", "ICCID", "SENHA"):
                ok, value, error = self.validate_field(field, vars_by_field[field].get())
                if not ok:
                    info_var.set(f"ERRO: {error}")
                    self.bell()
                    edit_entries[field].focus_set()
                    edit_entries[field].selection_range(0, "end")
                    return
                corrected[field] = value
            corrected["OPERADORA"] = self.identify_operator(corrected["ICCID"])

            if all(str(corrected.get(k) or "") == str(original.get(k) or "")
                   for k in ("SERIAL", "ICCID", "OPERADORA", "SENHA")):
                win.destroy()
                if self.scan_entries:
                    self.after(50, self.scan_entries[self.scan_sequence[0]].focus_set)
                return

            try:
                changed = self.store.edit_record(
                    self.current_eq_key,
                    self.current_lot,
                    self.username,
                    original.get("SERIAL", ""),
                    original.get("ICCID", ""),
                    corrected,
                )
            except (ValueError, TimeoutError, OSError) as exc:
                info_var.set(f"ERRO: {exc}")
                self.bell()
                return

            if not changed:
                messagebox.showerror(
                    "Não foi possível editar",
                    "A peça não foi encontrada no lote compartilhado. Aguarde a sincronização e tente novamente.",
                    parent=win,
                )
                return

            self.session_records[idx] = corrected
            self.refresh_session_table()
            self.refresh_live_counts()
            self.refresh_lots()
            self.scan_status.set(f"Peça corrigida ✓  —  BIPAR {self.scan_sequence[0]}")
            self.sync_status_var.set("Correção salva no lote compartilhado ✓")
            win.destroy()
            if self.scan_entries:
                self.after(50, self.scan_entries[self.scan_sequence[0]].focus_set)

        buttons = ttk.Frame(win)
        buttons.grid(row=row, column=0, columnspan=2, padx=18, pady=(4, 18), sticky="e")
        ttk.Button(buttons, text="Cancelar", command=cancel).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Salvar correção", command=save_edit).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", cancel)
        win.bind("<Escape>", lambda _e: cancel())
        win.bind("<Control-Return>", lambda _e: save_edit())
        win.wait_visibility()
        edit_entries["SERIAL"].focus_force()
        edit_entries["SERIAL"].selection_range(0, "end")
'''
if marker_delete not in source:
    raise SystemExit("Ponto de inserção da edição não encontrado")
source = source.replace(marker_delete, "\n" + edit_method + marker_delete, 1)

# Textos da configuração para refletir a nova proteção.
needle = '        ttk.Label(info, text="Exportação: modelo NF .xlsx + modelo de importação .xls da operadora configurada; dados gravados como TEXTO.").pack(anchor="w", pady=3)\n'
replacement = needle + '        ttk.Label(info, text="Correções: peças da sessão podem ser editadas; toda edição é validada, registrada no histórico e invalida exportação anterior.").pack(anchor="w", pady=3)\n'
if needle not in source:
    raise SystemExit("Bloco de informações de configuração não encontrado")
source = source.replace(needle, replacement, 1)

required = [
    'APP_VERSION = "0.2.6"',
    'def edit_record',
    'def edit_selected_session',
    'Editar selecionada',
    'Salvar correção',
    'dados_alterados_apos_exportacao',
    'historico',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.2.6 gerado com sucesso")
