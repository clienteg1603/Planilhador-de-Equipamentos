from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.3.4" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.3.4 não encontrado")

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


source = source.replace('APP_VERSION = "0.3.4"', 'APP_VERSION = "0.3.5"', 1)
if 'APP_VERSION = "0.3.5"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.3.5")

# -----------------------------------------------------------------------------
# Etapa 9 — robustez: integridade física dos JSONs, snapshot de exportação,
# diagnóstico local e endurecimento de exportação/finalização.
# -----------------------------------------------------------------------------
marker_submit = "\n    def submit(self, equipment_key: str, equipment_name: str, lot: str, username: str, records: list[dict]):\n"
helpers = r'''
    def lot_payload_issues(self, equipment_key: str, lot: str) -> list[str]:
        """Valida fisicamente os JSONs do lote sem esconder arquivo corrompido.

        load_records() continua tolerante para consulta, mas operações críticas
        (exportar/finalizar) usam esta checagem estrita para não considerar um
        arquivo quebrado como se simplesmente não existisse.
        """
        envios = self.lot_dir(equipment_key, lot) / "envios"
        if not envios.exists():
            return []
        issues = []
        for path in sorted(envios.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception as exc:
                issues.append(f"{path.name}: arquivo JSON ilegível ou inválido ({type(exc).__name__}).")
                continue
            if not isinstance(data, dict):
                issues.append(f"{path.name}: estrutura principal inválida.")
                continue
            regs = data.get("registros")
            if not isinstance(regs, list):
                issues.append(f"{path.name}: campo registros não é uma lista.")
                continue
            declared = data.get("quantidade", len(regs))
            try:
                declared = int(declared)
            except (TypeError, ValueError):
                declared = -1
            if declared != len(regs):
                issues.append(
                    f"{path.name}: quantidade declarada ({declared}) difere da quantidade real ({len(regs)})."
                )
            for idx, rec in enumerate(regs):
                if not isinstance(rec, dict):
                    issues.append(f"{path.name}: registro {idx + 1} possui estrutura inválida.")
                    break
        return issues

    def shared_write_probe(self) -> tuple[bool, str]:
        """Testa criação/gravação/remoção atômica na pasta compartilhada."""
        probe_dir = self.root / "configuracao"
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe = probe_dir / (".diagnostico_" + uuid.uuid4().hex + ".tmp")
        try:
            probe.write_text("ok " + now_iso(), encoding="utf-8")
            if not probe.exists() or not probe.read_text(encoding="utf-8").startswith("ok "):
                return False, "A pasta aceitou o arquivo, mas a leitura de conferência falhou."
            return True, "Leitura e gravação na pasta compartilhada: OK."
        except Exception as exc:
            return False, f"Falha de leitura/gravação na pasta compartilhada: {exc}"
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

    def health_report(self, equipments: dict) -> dict:
        report = {
            "write_ok": True,
            "write_message": "",
            "lots": 0,
            "records": 0,
            "conflicts": 0,
            "sync_reviews": 0,
            "post_finalize": 0,
            "payload_issues": [],
            "stale_locks": [],
        }
        report["write_ok"], report["write_message"] = self.shared_write_probe()
        base = self.root / "lotes"
        if not base.exists():
            return report
        for eqdir in sorted(base.iterdir()):
            if not eqdir.is_dir():
                continue
            for ldir in sorted(eqdir.iterdir()):
                if not ldir.is_dir():
                    continue
                eqkey = eqdir.name
                lot = ldir.name
                report["lots"] += 1
                payload = self.lot_payload_issues(eqkey, lot)
                for msg in payload:
                    report["payload_issues"].append(f"{eqkey} / {lot}: {msg}")
                records = self.load_records(eqkey, lot)
                report["records"] += len(records)
                report["conflicts"] += len(self.conflicts_from_records(records))
                report["sync_reviews"] += len(self.sync_review_records(eqkey, lot, records))
                if self.is_finalized(eqkey, lot):
                    integrity = self.finalization_integrity(eqkey, lot, records)
                    if integrity.get("changed"):
                        report["post_finalize"] += 1
                lock = ldir / ".lock"
                if lock.exists():
                    try:
                        age = time.time() - lock.stat().st_mtime
                        if age > 300:
                            report["stale_locks"].append(
                                f"{eqkey} / {lot}: lock com aproximadamente {int(age // 60)} min."
                            )
                    except OSError:
                        pass
        return report

'''
if marker_submit not in source:
    raise SystemExit("Ponto de inserção antes de submit não encontrado")
source = source.replace(marker_submit, "\n" + helpers + marker_submit, 1)

# Exportação registra fingerprint do conteúdo efetivamente exportado.
new_mark_exported = r'''    def mark_exported(
        self,
        equipment_key: str,
        lot: str,
        count: int,
        files: list[str],
        username: str = "",
        destination: str = "",
        fingerprint: str = "",
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
            "fingerprint": str(fingerprint or ""),
        }
        history.append(entry)
        history = history[-30:]
        meta.update({
            "ultima_exportacao_em": exported_at,
            "ultima_exportacao_por": str(username or "").strip(),
            "ultima_exportacao_quantidade": int(count),
            "ultima_exportacao_pasta": str(destination or "").strip(),
            "ultima_exportacao_fingerprint": str(fingerprint or ""),
            "arquivos": [str(x) for x in files],
            "historico_exportacoes": history,
            "dados_alterados_apos_exportacao": False,
        })
        atomic_json_write(self.meta_path(equipment_key, lot), meta)
'''
sub_once(
    r'    def mark_exported\(.*?(?=\n    def finalize\()',
    new_mark_exported,
    "mark_exported com fingerprint",
)

# Finalização faz auditoria estrita e, quando disponível, exige o mesmo conteúdo
# (não apenas a mesma quantidade) da última exportação.
new_finalize = r'''    def finalize(self, equipment_key: str, lot: str, username: str):
        with self.lot_lock(equipment_key, lot):
            if self.is_finalized(equipment_key, lot):
                integrity = self.finalization_integrity(equipment_key, lot)
                if integrity.get("changed"):
                    raise ValueError(
                        "O lote já estava finalizado, mas mudou após a finalização. "
                        "Use Conflitos para revisar antes de continuar."
                    )
                return

            payload_issues = self.lot_payload_issues(equipment_key, lot)
            if payload_issues:
                preview = "\n".join(payload_issues[:5])
                raise ValueError(
                    "Há arquivo(s) de dados com problema no lote. A finalização foi bloqueada.\n\n" + preview
                )

            records = self.load_records(equipment_key, lot)
            count = len(records)
            if count == 0:
                raise ValueError("O lote está vazio.")

            conflicts = self.conflicts_from_records(records)
            if conflicts:
                raise ValueError(
                    f"Existem {len(conflicts)} conflito(s) de SERIAL/ICCID. "
                    "Resolva os conflitos antes de finalizar."
                )
            review = self.sync_review_records(equipment_key, lot, records)
            if review:
                raise ValueError(
                    f"Existem {len(review)} registro(s) aguardando revisão de sincronização. "
                    "Resolva a revisão antes de finalizar."
                )

            meta = self.load_meta(equipment_key, lot)
            last_count = int(meta.get("ultima_exportacao_quantidade", -1) or -1)
            if bool(meta.get("dados_alterados_apos_exportacao")) or last_count != count:
                raise ValueError(
                    "O lote mudou desde a última exportação (ou ainda não foi exportado). "
                    "Exporte novamente antes de finalizar."
                )

            current_fp = self.records_fingerprint(records)
            exported_fp = str(meta.get("ultima_exportacao_fingerprint") or "")
            if exported_fp and exported_fp != current_fp:
                raise ValueError(
                    "A quantidade não mudou, mas o conteúdo do lote está diferente da última exportação. "
                    "Exporte novamente antes de finalizar."
                )

            atomic_json_write(self.lot_dir(equipment_key, lot) / "finalizado.json", {
                "finalizado_em": now_iso(),
                "finalizado_por": username,
                "quantidade": count,
                "fingerprint": current_fp,
                "assinaturas_envio": self.source_signatures(records),
                "versao_programa": APP_VERSION,
            })
'''
sub_once(r'    def finalize\(self, equipment_key: str, lot: str, username: str\):.*?(?=\n    def list_lots\()', new_finalize, "finalize robusto")

# A conferência de exportação também enxerga arquivos fisicamente inválidos.
needle_preflight = '        if not records:\n            issues.append("O lote está vazio.")\n\n        conflicts = self.store.conflicts_from_records(records)\n'
replacement_preflight = r'''        if not records:
            issues.append("O lote está vazio.")

        payload_issues = self.store.lot_payload_issues(info.equipment_key, info.lot)
        if payload_issues:
            issues.append(
                f"Existem {len(payload_issues)} problema(s) físico(s) nos arquivos de dados do lote. "
                "Execute o diagnóstico em Configurações."
            )

        conflicts = self.store.conflicts_from_records(records)
'''
replace_once(needle_preflight, replacement_preflight, "payload issues no preflight")

# Snapshot duplo: se o OneDrive trouxer/alterar dados enquanto o Excel está sendo
# gerado, os arquivos não são marcados como exportação válida.
pattern_export = r'''                files = exporter\.export\(info\.lot, records, destination\)\n                self\.store\.mark_exported\(\n                    info\.equipment_key,\n                    info\.lot,\n                    len\(records\),\n                    \[str\(p\) for p in files\],\n                    username=self\.username,\n                    destination=str\(destination\),\n                \)'''
replacement_export = r'''                export_fingerprint = self.store.records_fingerprint(records)
                files = exporter.export(info.lot, records, destination)

                # Confere novamente depois da geração do Excel. Em OneDrive o lote
                # pode mudar durante os segundos em que o Excel está trabalhando.
                after_records = self.store.load_records(info.equipment_key, info.lot)
                after_payload = self.store.lot_payload_issues(info.equipment_key, info.lot)
                after_fingerprint = self.store.records_fingerprint(after_records)
                after_conflicts = self.store.conflicts_from_records(after_records)
                after_review = self.store.sync_review_records(info.equipment_key, info.lot, after_records)
                if (
                    after_payload
                    or after_conflicts
                    or after_review
                    or after_fingerprint != export_fingerprint
                ):
                    raise RuntimeError(
                        "O lote mudou ou recebeu uma pendência enquanto as planilhas estavam sendo geradas.\n\n"
                        "Os arquivos podem ter sido criados na pasta escolhida, mas NÃO foram marcados como "
                        "exportação válida. Atualize a Central, resolva qualquer pendência e exporte novamente."
                    )

                self.store.mark_exported(
                    info.equipment_key,
                    info.lot,
                    len(records),
                    [str(p) for p in files],
                    username=self.username,
                    destination=str(destination),
                    fingerprint=export_fingerprint,
                )'''
sub_once(pattern_export, replacement_export, "snapshot pós-exportação")

# Diagnóstico acessível em Configurações.
settings_marker = "    # ---------------- Configurações ----------------\n"
diagnostic_method = r'''    def run_robustness_diagnostics(self):
        try:
            report = self.store.health_report(self.equipments)
        except Exception as exc:
            messagebox.showerror("Diagnóstico", f"Não foi possível executar o diagnóstico:\n{exc}")
            return

        template_issues = []
        for key, cfg in self.equipments.items():
            name = str(cfg.get("nome") or key)
            exports = cfg.get("exportacoes") or {}
            nf = str(((exports.get("nf") or {}).get("template") or "")).strip()
            if nf:
                try:
                    if not self._resolve_template_path(nf).exists():
                        template_issues.append(f"{name}: modelo Mestre/NF não encontrado.")
                except Exception:
                    template_issues.append(f"{name}: caminho do modelo Mestre/NF inválido.")
            imp = (exports.get("importacao") or {}).get("templates_por_operadora") or {}
            for op, rel in sorted(imp.items()):
                try:
                    if rel and not self._resolve_template_path(str(rel)).exists():
                        template_issues.append(f"{name}: modelo de importação {op} não encontrado.")
                except Exception:
                    template_issues.append(f"{name}: caminho do modelo de importação {op} inválido.")

        critical = (
            (not report["write_ok"])
            or bool(report["payload_issues"])
            or bool(report["post_finalize"])
            or bool(template_issues)
        )
        warnings = report["conflicts"] + report["sync_reviews"] + len(report["stale_locks"])

        win = tk.Toplevel(self)
        win.title("Diagnóstico de robustez")
        win.geometry("820x620")
        win.minsize(700, 500)
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Diagnóstico de robustez", style="PageTitle.TLabel").pack(
            anchor="w", padx=16, pady=(16, 3)
        )
        if critical:
            headline = "ATENÇÃO — há item(ns) que podem bloquear exportação/finalização."
            headline_style = "ScanError.TLabel"
        elif warnings:
            headline = "Diagnóstico concluído com pendências operacionais para revisar."
            headline_style = "ScanInfo.TLabel"
        else:
            headline = "Diagnóstico concluído — nenhum problema detectado."
            headline_style = "ScanSuccess.TLabel"
        ttk.Label(win, text=headline, style=headline_style).pack(anchor="w", padx=16, pady=(0, 10))

        summary = ttk.LabelFrame(win, text="Resumo", padding=10)
        summary.pack(fill="x", padx=16, pady=(0, 10))
        ttk.Label(summary, text=report["write_message"]).pack(anchor="w")
        ttk.Label(
            summary,
            text=(
                f"Lotes: {report['lots']}   •   Registros lidos: {report['records']}   •   "
                f"Conflitos: {report['conflicts']}   •   Revisões de sincronização: {report['sync_reviews']}"
            ),
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            summary,
            text=f"Alterações pós-finalização: {report['post_finalize']}   •   Locks antigos: {len(report['stale_locks'])}",
        ).pack(anchor="w", pady=(4, 0))

        details = ttk.LabelFrame(win, text="Detalhes", padding=10)
        details.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        text = tk.Text(details, wrap="word", height=18)
        scroll = ttk.Scrollbar(details, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        lines = []
        if report["payload_issues"]:
            lines.append("ARQUIVOS DE DADOS COM PROBLEMA:")
            lines.extend("  • " + x for x in report["payload_issues"])
            lines.append("")
        if report["post_finalize"]:
            lines.append(
                f"• {report['post_finalize']} lote(s) finalizado(s) mudaram depois da finalização. "
                "Abra a Central > Conflitos para revisar."
            )
        if report["conflicts"]:
            lines.append(f"• {report['conflicts']} conflito(s) de SERIAL/ICCID detectado(s).")
        if report["sync_reviews"]:
            lines.append(f"• {report['sync_reviews']} registro(s) aguardando revisão de sincronização.")
        if report["stale_locks"]:
            lines.append("LOCKS ANTIGOS:")
            lines.extend("  • " + x for x in report["stale_locks"])
        if template_issues:
            lines.append("MODELOS DE EXPORTAÇÃO:")
            lines.extend("  • " + x for x in template_issues)
        if not lines:
            lines.append(
                "Nenhuma inconsistência foi detectada nos dados atualmente visíveis neste PC.\n\n"
                "Observação: com OneDrive, outro computador ainda pode ter arquivos aguardando sincronização. "
                "Este diagnóstico verifica o estado que já chegou a este computador."
            )
        text.insert("1.0", "\n".join(lines))
        text.config(state="disabled")

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(bottom, text="Atualizar Central", command=lambda: (self.refresh_lots(), win.destroy())).pack(side="left")
        ttk.Button(bottom, text="Fechar", command=win.destroy, style="Primary.TButton").pack(side="right")

'''
if settings_marker not in source:
    raise SystemExit("Marcador de Configurações não encontrado")
source = source.replace(settings_marker, diagnostic_method + settings_marker, 1)

needle_info = '        info = ttk.LabelFrame(self.tab_settings, text="Configuração atual", padding=14)\n'
diagnostic_box = r'''        robustness = ttk.LabelFrame(self.tab_settings, text="Diagnóstico e robustez", padding=14)
        robustness.pack(fill="x", pady=(14, 0))
        ttk.Label(
            robustness,
            text=(
                "Verifica gravação na pasta compartilhada, arquivos JSON, conflitos, revisões de sincronização, "
                "alterações pós-finalização, locks antigos e modelos de exportação."
            ),
            wraplength=900,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Button(
            robustness,
            text="Executar diagnóstico",
            command=self.run_robustness_diagnostics,
            style="Primary.TButton",
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            robustness,
            text="O diagnóstico não apaga nem corrige dados automaticamente.",
            style="Muted.TLabel",
        ).grid(row=1, column=1, sticky="w", padx=(10, 0))

'''
replace_once(needle_info, diagnostic_box + needle_info, "quadro de diagnóstico")

required = [
    'APP_VERSION = "0.3.5"',
    'def lot_payload_issues',
    'def health_report',
    'ultima_exportacao_fingerprint',
    'after_fingerprint != export_fingerprint',
    'def run_robustness_diagnostics',
    'Executar diagnóstico',
    'versao_programa',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.5 gerado com sucesso — Etapa 9 robustez")
