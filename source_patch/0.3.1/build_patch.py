from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.3.0" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.3.0 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.3.0"', 'APP_VERSION = "0.3.1"', 1)
if 'APP_VERSION = "0.3.1"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# Etapa 6 — Exportação: histórico, pasta lembrada e auditoria pré-exportação.
# -----------------------------------------------------------------------------
new_mark_exported = r'''    def mark_exported(
        self,
        equipment_key: str,
        lot: str,
        count: int,
        files: list[str],
        username: str = "",
        destination: str = "",
    ):
        meta = self.load_meta(equipment_key, lot)
        exported_at = now_iso()
        history = list(meta.get("historico_exportacoes") or [])
        entry = {
            "exportado_em": exported_at,
            "exportado_por": str(username or "").strip(),
            "quantidade": int(count),
            "pasta": str(destination or "").strip(),
            "arquivos": [str(x) for x in files],
        }
        history.append(entry)
        # Mantém um histórico útil sem deixar o meta.json crescer indefinidamente.
        history = history[-30:]
        meta.update({
            "ultima_exportacao_em": exported_at,
            "ultima_exportacao_por": str(username or "").strip(),
            "ultima_exportacao_quantidade": int(count),
            "ultima_exportacao_pasta": str(destination or "").strip(),
            "arquivos": [str(x) for x in files],
            "historico_exportacoes": history,
            "dados_alterados_apos_exportacao": False,
        })
        atomic_json_write(self.meta_path(equipment_key, lot), meta)
'''
sub_once(
    r'    def mark_exported\(.*?(?=\n    def finalize\()',
    new_mark_exported,
    "mark_exported com histórico",
)

# Botão para abrir a última pasta exportada diretamente pela Central.
needle_button = '        self.central_conflict_btn.pack(side="left", padx=(6, 0))\n'
button_add = needle_button + (
    '        self.central_open_export_btn = ttk.Button(toolbar, text="Abrir última pasta", '
    'command=self.open_last_export_folder, state="disabled")\n'
    '        self.central_open_export_btn.pack(side="left", padx=(6, 0))\n'
)
if needle_button not in source:
    raise SystemExit("Botão Conflitos da Central não encontrado")
source = source.replace(needle_button, button_add, 1)

new_action_state = r'''    def _update_central_action_state(self, *_):
        info = self._central_selected_info_silent()
        buttons = (
            getattr(self, "central_view_btn", None),
            getattr(self, "central_export_btn", None),
            getattr(self, "central_finalize_btn", None),
            getattr(self, "central_conflict_btn", None),
            getattr(self, "central_open_export_btn", None),
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
        meta = self.store.load_meta(info.equipment_key, info.lot)
        last_folder = str(meta.get("ultima_exportacao_pasta") or "").strip()

        self.central_view_btn.config(state="normal")
        self.central_export_btn.config(state="normal" if can_export else "disabled")
        self.central_finalize_btn.config(state="normal" if can_finalize else "disabled")
        self.central_conflict_btn.config(state="normal" if issue else "disabled")
        self.central_open_export_btn.config(state="normal" if last_folder else "disabled")

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
'''
sub_once(
    r'    def _update_central_action_state\(self, \*_\):.*?(?=\n    def build_central_tab\()',
    new_action_state,
    "estado das ações da Central",
)

new_export_block = r'''    def _export_preflight(self, info: LotInfo) -> dict:
        records = self.store.load_records(info.equipment_key, info.lot)
        meta = self.store.load_meta(info.equipment_key, info.lot)
        cfg = self.equipments[info.equipment_key]
        exports = cfg.get("exportacoes", {})
        issues = []
        warnings = []

        operator_counts = {}
        for rec in records:
            op = str(rec.get("OPERADORA") or "").strip().upper() or "SEM OPERADORA"
            operator_counts[op] = operator_counts.get(op, 0) + 1

        if not records:
            issues.append("O lote está vazio.")

        conflicts = self.store.conflicts_from_records(records)
        if conflicts:
            issues.append(f"Existem {len(conflicts)} conflito(s) de SERIAL/ICCID no lote.")

        review = self.store.sync_review_records(info.equipment_key, info.lot, records)
        if review:
            issues.append(f"Existem {len(review)} registro(s) aguardando revisão de sincronização.")

        finalized = self.store.is_finalized(info.equipment_key, info.lot)
        if finalized:
            integrity = self.store.finalization_integrity(info.equipment_key, info.lot, records)
            if integrity.get("changed"):
                issues.append("O lote mudou depois da finalização. Reabra e corrija antes de exportar.")

        nf_cfg = exports.get("nf") or {}
        nf_rel = str(nf_cfg.get("template") or "").strip()
        nf_path = self.base_dir / nf_rel if nf_rel else None
        nf_ok = bool(nf_path and nf_path.exists())
        if not nf_ok:
            issues.append("O modelo Mestre/NF não foi encontrado para este equipamento.")

        import_cfg = exports.get("importacao") or {}
        template_map = import_cfg.get("templates_por_operadora", {}) or {}
        operator_models = []
        for op in sorted(operator_counts):
            rel = str(template_map.get(op) or "").strip()
            path = self.base_dir / rel if rel else None
            exists = bool(path and path.exists())
            operator_models.append({
                "operadora": op,
                "quantidade": operator_counts[op],
                "modelo": path.name if path else "NÃO CONFIGURADO",
                "ok": exists,
            })
            if not exists:
                issues.append(f"Não existe modelo de importação disponível para a operadora {op}.")

        last_count = int(meta.get("ultima_exportacao_quantidade", 0) or 0)
        changed_flag = bool(meta.get("dados_alterados_apos_exportacao"))
        if not last_count:
            export_state = "Ainda não exportado."
        elif last_count == len(records) and not changed_flag:
            export_state = f"Última exportação está compatível com os {len(records)} registros atuais."
        else:
            export_state = (
                f"REEXPORTAÇÃO NECESSÁRIA — última exportação: {last_count}; "
                f"estado atual: {len(records)} registro(s)."
            )
            warnings.append(export_state)

        if finalized and not issues:
            warnings.append("Este lote já está finalizado; a reexportação não reabre o lote.")

        return {
            "records": records,
            "meta": meta,
            "issues": issues,
            "warnings": warnings,
            "ready": bool(records) and not issues,
            "operator_counts": operator_counts,
            "operator_models": operator_models,
            "nf_model": nf_path.name if nf_path else "NÃO CONFIGURADO",
            "nf_ok": nf_ok,
            "export_state": export_state,
            "history_count": len(meta.get("historico_exportacoes") or []),
        }

    def _open_folder(self, folder: str | Path):
        path = Path(folder)
        if not path.exists() or not path.is_dir():
            messagebox.showwarning(
                "Abrir pasta",
                "A pasta da última exportação não está disponível neste computador.\n\n"
                f"Caminho registrado:\n{path}",
            )
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Abrir pasta", f"Não foi possível abrir a pasta:\n{exc}")

    def open_last_export_folder(self):
        info = self.selected_lot_info()
        if not info:
            return
        meta = self.store.load_meta(info.equipment_key, info.lot)
        folder = str(meta.get("ultima_exportacao_pasta") or "").strip()
        if not folder:
            messagebox.showinfo("Exportação", "Este lote ainda não possui uma pasta de exportação registrada.")
            return
        self._open_folder(folder)

    def export_selected_lot(self):
        info = self.selected_lot_info()
        if not info:
            return

        check = self._export_preflight(info)
        meta = check["meta"]

        win = tk.Toplevel(self)
        win.title(f"Conferência de exportação — {info.equipment_name} — Lote {info.lot}")
        win.geometry("780x600")
        win.minsize(700, 520)
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Conferência antes da exportação", font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=16, pady=(16, 4)
        )
        ttk.Label(
            win,
            text=f"{info.equipment_name}  •  Lote {info.lot}  •  {len(check['records'])} registro(s)",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(0, 10))

        state_text = "PRONTO PARA EXPORTAR" if check["ready"] else "EXPORTAÇÃO BLOQUEADA"
        state_style = "ScanSuccess.TLabel" if check["ready"] else "ScanError.TLabel"
        ttk.Label(win, text=state_text, style=state_style).pack(anchor="w", padx=16, pady=(0, 6))
        ttk.Label(win, text=check["export_state"], wraplength=740).pack(anchor="w", padx=16, pady=(0, 10))

        models = ttk.LabelFrame(win, text="Modelos que serão usados", padding=10)
        models.pack(fill="x", padx=16, pady=(0, 10))
        nf_status = "OK" if check["nf_ok"] else "AUSENTE"
        ttk.Label(models, text=f"Mestre/NF: {check['nf_model']}  —  {nf_status}").pack(anchor="w", pady=(0, 6))

        cols = ("operadora", "quantidade", "modelo", "situacao")
        tree = ttk.Treeview(models, columns=cols, show="headings", height=max(2, min(6, len(check["operator_models"]))))
        headings = {"operadora":"OPERADORA", "quantidade":"REGISTROS", "modelo":"MODELO DE IMPORTAÇÃO", "situacao":"SITUAÇÃO"}
        widths = {"operadora":110, "quantidade":90, "modelo":330, "situacao":100}
        for col in cols:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="center")
        for item in check["operator_models"]:
            tree.insert("", "end", values=(
                item["operadora"], item["quantidade"], item["modelo"], "OK" if item["ok"] else "AUSENTE"
            ))
        tree.pack(fill="x")

        last = ttk.LabelFrame(win, text="Última exportação", padding=10)
        last.pack(fill="x", padx=16, pady=(0, 10))
        last_at = str(meta.get("ultima_exportacao_em") or "Nunca").replace("T", " ")
        last_by = str(meta.get("ultima_exportacao_por") or "—")
        last_count = int(meta.get("ultima_exportacao_quantidade", 0) or 0)
        last_folder = str(meta.get("ultima_exportacao_pasta") or "—")
        ttk.Label(last, text=f"Quando: {last_at}   •   Por: {last_by}   •   Registros: {last_count}").pack(anchor="w")
        ttk.Label(last, text=f"Pasta: {last_folder}", wraplength=720).pack(anchor="w", pady=(4, 0))
        ttk.Label(last, text=f"Exportações registradas neste lote: {check['history_count']}").pack(anchor="w", pady=(4, 0))

        messages = ttk.LabelFrame(win, text="Verificação", padding=10)
        messages.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        text = tk.Text(messages, height=7, wrap="word")
        text.pack(fill="both", expand=True)
        lines = []
        if check["issues"]:
            lines.extend([f"BLOQUEIO: {x}" for x in check["issues"]])
        if check["warnings"]:
            lines.extend([f"ATENÇÃO: {x}" for x in check["warnings"]])
        if not lines:
            lines.append("Tudo certo. Os arquivos podem ser gerados.")
        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side="right")

        def begin_export():
            if not check["ready"]:
                return
            preferred = str(meta.get("ultima_exportacao_pasta") or self.settings.get("ultima_pasta_exportacao") or "").strip()
            kwargs = {"title": "Escolha a pasta onde serão salvas as planilhas", "parent": win}
            if preferred and Path(preferred).exists():
                kwargs["initialdir"] = preferred
            destination = filedialog.askdirectory(**kwargs)
            if not destination:
                return
            win.destroy()
            self._perform_export(info, Path(destination))

        export_btn = ttk.Button(buttons, text="Exportar agora", command=begin_export)
        export_btn.pack(side="right", padx=(0, 8))
        if not check["ready"]:
            export_btn.config(state="disabled")

    def _perform_export(self, info: LotInfo, destination: Path):
        files = []
        try:
            with self.store.lot_lock(info.equipment_key, info.lot):
                # Revalida no instante da exportação para não confiar apenas na tela de conferência.
                records = self.store.load_records(info.equipment_key, info.lot)
                conflicts = self.store.conflicts_from_records(records)
                review = self.store.sync_review_records(info.equipment_key, info.lot, records)
                if conflicts:
                    raise ValueError("A exportação foi cancelada porque surgiu um conflito de SERIAL/ICCID.")
                if review:
                    raise ValueError("A exportação foi cancelada porque surgiram registros aguardando revisão de sincronização.")
                if self.store.is_finalized(info.equipment_key, info.lot):
                    integrity = self.store.finalization_integrity(info.equipment_key, info.lot, records)
                    if integrity.get("changed"):
                        raise ValueError("O lote mudou após a finalização. Reabra e corrija antes de exportar.")

                # Valida novamente a existência dos modelos antes de abrir o Excel.
                live_info = next(
                    (x for x in self.store.list_lots(self.equipments)
                     if x.equipment_key == info.equipment_key and x.lot == info.lot),
                    info,
                )
                check = self._export_preflight(live_info)
                if not check["ready"]:
                    raise ValueError("\n".join(check["issues"]))

                exporter = ExcelExporter(self.base_dir, self.equipments[info.equipment_key])
                files = exporter.export(info.lot, records, destination)
                self.store.mark_exported(
                    info.equipment_key,
                    info.lot,
                    len(records),
                    [str(p) for p in files],
                    username=self.username,
                    destination=str(destination),
                )
        except Exception as exc:
            messagebox.showerror("Falha na exportação", str(exc))
            self.refresh_lots()
            return

        self.settings["ultima_pasta_exportacao"] = str(destination)
        self.save_local_settings()
        self.refresh_lots()

        names = "\n".join(f"• {p.name}" for p in files)
        open_now = messagebox.askyesno(
            "Exportação concluída",
            f"Arquivos gerados com sucesso:\n\n{names}\n\n"
            f"Pasta:\n{destination}\n\nDeseja abrir a pasta agora?",
        )
        if open_now:
            self._open_folder(destination)

        if not self.store.is_finalized(info.equipment_key, info.lot):
            if messagebox.askyesno(
                "Finalizar lote",
                "A exportação está atualizada. Deseja finalizar este lote agora?\n\n"
                "Depois de finalizado, nenhum PC poderá adicionar novas peças.",
            ):
                self._finalize(info)
'''
sub_once(
    r'    def export_selected_lot\(self\):.*?(?=\n    def finalize_selected_lot\()',
    new_export_block,
    "fluxo de exportação",
)

required = [
    'APP_VERSION = "0.3.1"',
    'Conferência antes da exportação',
    'def _export_preflight',
    'def _perform_export',
    'Abrir última pasta',
    'historico_exportacoes',
    'ultima_exportacao_pasta',
    'ultima_pasta_exportacao',
    'REEXPORTAÇÃO NECESSÁRIA',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.1 gerado com sucesso")
