from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.2.6" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.2.6 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.2.6"', 'APP_VERSION = "0.2.7"', 1)
if 'APP_VERSION = "0.2.7"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# Metadados do lote: conflitos e alteração sincronizada após finalização.
# -----------------------------------------------------------------------------
old_dataclass = '''    last_export_count: int\n    finalized: bool\n\n\nclass DataStore:'''
new_dataclass = '''    last_export_count: int\n    finalized: bool\n    conflict_count: int = 0\n    post_finalize_changed: bool = False\n    sync_review_count: int = 0\n\n\nclass DataStore:'''
if old_dataclass not in source:
    raise SystemExit("LotInfo não encontrado")
source = source.replace(old_dataclass, new_dataclass, 1)

# Cada registro passa a carregar origem e localização exata dentro do arquivo de envio.
new_load_records = r'''    def load_records(self, equipment_key: str, lot: str) -> list[dict]:
        envios = self.lot_dir(equipment_key, lot) / "envios"
        if not envios.exists():
            return []
        records = []
        for p in sorted(envios.glob("*.json")):
            data = read_json(p, {}) or {}
            user = data.get("usuario", "")
            sent_at = data.get("enviado_em", "")
            origin = data.get("origem_pc", "")
            for rec_index, rec in enumerate(data.get("registros", []) or []):
                item = dict(rec)
                item["_usuario"] = user
                item["_enviado_em"] = sent_at
                item["_origem_pc"] = origin
                item["_arquivo_envio"] = p.name
                item["_indice_envio"] = rec_index
                records.append(item)
        return records
'''
sub_once(r'    def load_records\(self, equipment_key: str, lot: str\) -> list\[dict\]:.*?(?=\n    @staticmethod\n    def duplicate_messages)', new_load_records, "load_records")

# Camada de detecção e resolução segura de conflitos sincronizados.
marker_submit = "\n    def submit(self, equipment_key: str, equipment_name: str, lot: str, username: str, records: list[dict]):\n"
helpers = r'''
    @staticmethod
    def computer_name() -> str:
        return str(os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "PC desconhecido").strip()

    @staticmethod
    def records_fingerprint(records: list[dict]) -> str:
        rows = []
        for r in records:
            rows.append({
                "SERIAL": str(r.get("SERIAL") or ""),
                "ICCID": str(r.get("ICCID") or ""),
                "OPERADORA": str(r.get("OPERADORA") or ""),
                "SENHA": str(r.get("SENHA") or ""),
                "usuario": str(r.get("_usuario") or ""),
                "origem_pc": str(r.get("_origem_pc") or ""),
                "arquivo": str(r.get("_arquivo_envio") or ""),
                "indice": int(r.get("_indice_envio", 0) or 0),
            })
        rows.sort(key=lambda x: (x["arquivo"], x["indice"], x["SERIAL"], x["ICCID"]))
        raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def source_signatures(records: list[dict]) -> dict:
        grouped = {}
        for r in records:
            name = str(r.get("_arquivo_envio") or "")
            if not name:
                continue
            grouped.setdefault(name, []).append({
                "SERIAL": str(r.get("SERIAL") or ""),
                "ICCID": str(r.get("ICCID") or ""),
                "OPERADORA": str(r.get("OPERADORA") or ""),
                "SENHA": str(r.get("SENHA") or ""),
                "usuario": str(r.get("_usuario") or ""),
                "origem_pc": str(r.get("_origem_pc") or ""),
                "indice": int(r.get("_indice_envio", 0) or 0),
            })
        result = {}
        for name, rows in grouped.items():
            rows.sort(key=lambda x: x["indice"])
            raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            result[name] = hashlib.sha256(raw).hexdigest()
        return result

    @staticmethod
    def conflicts_from_records(records: list[dict]) -> list[dict]:
        buckets = {"SERIAL": {}, "ICCID": {}}
        for r in records:
            serial = str(r.get("SERIAL") or "").strip().upper()
            iccid = str(r.get("ICCID") or "").strip()
            if serial:
                buckets["SERIAL"].setdefault(serial, []).append(r)
            if iccid:
                buckets["ICCID"].setdefault(iccid, []).append(r)
        conflicts = []
        for field in ("SERIAL", "ICCID"):
            for value, items in sorted(buckets[field].items()):
                if len(items) > 1:
                    conflicts.append({"campo": field, "valor": value, "registros": [dict(x) for x in items]})
        return conflicts

    def find_conflicts(self, equipment_key: str, lot: str) -> list[dict]:
        return self.conflicts_from_records(self.load_records(equipment_key, lot))

    def finalization_integrity(self, equipment_key: str, lot: str, records: list[dict] | None = None) -> dict:
        final_path = self.lot_dir(equipment_key, lot) / "finalizado.json"
        if not final_path.exists():
            return {"finalized": False, "changed": False, "suspect_records": [], "reason": ""}
        final_data = read_json(final_path, {}) or {}
        records = self.load_records(equipment_key, lot) if records is None else records
        current_count = len(records)
        expected_count = int(final_data.get("quantidade", current_count) or 0)
        expected_fp = str(final_data.get("fingerprint") or "")
        current_fp = self.records_fingerprint(records)
        expected_sources = dict(final_data.get("assinaturas_envio") or {})
        current_sources = self.source_signatures(records)

        changed_sources = set()
        if expected_sources:
            for name in set(expected_sources) | set(current_sources):
                if expected_sources.get(name) != current_sources.get(name):
                    changed_sources.add(name)
        suspect_records = [dict(r) for r in records if str(r.get("_arquivo_envio") or "") in changed_sources]

        changed = current_count != expected_count
        if expected_fp and current_fp != expected_fp:
            changed = True
        if expected_sources and changed_sources:
            changed = True

        reasons = []
        if current_count != expected_count:
            reasons.append(f"quantidade finalizada {expected_count}, quantidade atual {current_count}")
        if expected_fp and current_fp != expected_fp:
            reasons.append("conteúdo do lote mudou após a finalização")
        if changed_sources:
            reasons.append(f"{len(changed_sources)} arquivo(s) de envio mudaram ou chegaram depois")
        return {
            "finalized": True,
            "changed": changed,
            "expected_count": expected_count,
            "current_count": current_count,
            "suspect_records": suspect_records,
            "changed_sources": sorted(changed_sources),
            "reason": "; ".join(reasons),
            "final_data": final_data,
        }

    def sync_review_records(self, equipment_key: str, lot: str, records: list[dict] | None = None) -> list[dict]:
        meta = self.load_meta(equipment_key, lot)
        refs = list(meta.get("registros_suspeitos_sincronizacao") or [])
        if not refs:
            return []
        wanted = {(str(x.get("arquivo") or ""), int(x.get("indice", 0) or 0)) for x in refs}
        records = self.load_records(equipment_key, lot) if records is None else records
        return [dict(r) for r in records if (str(r.get("_arquivo_envio") or ""), int(r.get("_indice_envio", 0) or 0)) in wanted]

    def _mark_changed_after_export(self, equipment_key: str, lot: str):
        meta = self.load_meta(equipment_key, lot)
        if int(meta.get("ultima_exportacao_quantidade", 0) or 0) > 0:
            meta["dados_alterados_apos_exportacao"] = True
            meta["ultima_alteracao_em"] = now_iso()
            atomic_json_write(self.meta_path(equipment_key, lot), meta)

    def _clear_sync_review_ref(self, equipment_key: str, lot: str, source_file: str, record_index: int):
        meta = self.load_meta(equipment_key, lot)
        refs = list(meta.get("registros_suspeitos_sincronizacao") or [])
        keep = [x for x in refs if not (
            str(x.get("arquivo") or "") == str(source_file or "") and
            int(x.get("indice", 0) or 0) == int(record_index)
        )]
        if len(keep) != len(refs):
            meta["registros_suspeitos_sincronizacao"] = keep
            if not keep:
                meta.pop("reaberto_por_conflito", None)
            atomic_json_write(self.meta_path(equipment_key, lot), meta)

    def edit_record_by_source(self, equipment_key: str, lot: str, source_file: str, record_index: int,
                              new_record: dict, actor: str) -> bool:
        with self.lot_lock(equipment_key, lot):
            if self.is_finalized(equipment_key, lot):
                raise ValueError("O lote está finalizado. Reabra o lote pelo painel de conflitos antes de corrigir.")
            envios = self.lot_dir(equipment_key, lot) / "envios"
            path = envios / Path(str(source_file)).name
            data = read_json(path, {}) or {}
            records = list(data.get("registros", []) or [])
            idx = int(record_index)
            if idx < 0 or idx >= len(records):
                return False
            old_record = dict(records[idx])

            existing = [r for r in self.load_records(equipment_key, lot) if not (
                str(r.get("_arquivo_envio") or "") == path.name and
                int(r.get("_indice_envio", 0) or 0) == idx
            )]
            clean_new = {
                "SERIAL": str(new_record.get("SERIAL") or ""),
                "ICCID": str(new_record.get("ICCID") or ""),
                "OPERADORA": str(new_record.get("OPERADORA") or ""),
                "SENHA": str(new_record.get("SENHA") or ""),
            }
            dup = self.duplicate_messages(existing, [clean_new])
            if dup:
                raise ValueError("\n".join(dup))
            records[idx] = clean_new
            data["registros"] = records
            data["quantidade"] = len(records)
            data["ultima_correcao_em"] = now_iso()
            atomic_json_write(path, data)

            history = self.lot_dir(equipment_key, lot) / "historico"
            history.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_conflito_edicao_" + uuid.uuid4().hex[:8] + ".json"
            atomic_json_write(history / name, {
                "tipo": "CORRECAO_CONFLITO",
                "editado_em": now_iso(),
                "corrigido_por": actor,
                "usuario_original": data.get("usuario", ""),
                "origem_pc": data.get("origem_pc", ""),
                "arquivo_envio": path.name,
                "indice": idx,
                "antes": old_record,
                "depois": clean_new,
            })
            self._mark_changed_after_export(equipment_key, lot)
            self._clear_sync_review_ref(equipment_key, lot, path.name, idx)
            return True

    def delete_record_by_source(self, equipment_key: str, lot: str, source_file: str, record_index: int,
                                actor: str) -> bool:
        with self.lot_lock(equipment_key, lot):
            if self.is_finalized(equipment_key, lot):
                raise ValueError("O lote está finalizado. Reabra o lote pelo painel de conflitos antes de excluir.")
            envios = self.lot_dir(equipment_key, lot) / "envios"
            path = envios / Path(str(source_file)).name
            data = read_json(path, {}) or {}
            records = list(data.get("registros", []) or [])
            idx = int(record_index)
            if idx < 0 or idx >= len(records):
                return False
            removed = dict(records.pop(idx))
            if records:
                data["registros"] = records
                data["quantidade"] = len(records)
                atomic_json_write(path, data)
            else:
                path.unlink(missing_ok=True)

            history = self.lot_dir(equipment_key, lot) / "historico"
            history.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_conflito_exclusao_" + uuid.uuid4().hex[:8] + ".json"
            atomic_json_write(history / name, {
                "tipo": "EXCLUSAO_CONFLITO",
                "excluido_em": now_iso(),
                "excluido_por": actor,
                "usuario_original": data.get("usuario", ""),
                "origem_pc": data.get("origem_pc", ""),
                "arquivo_envio": path.name,
                "indice": idx,
                "registro": removed,
            })
            self._mark_changed_after_export(equipment_key, lot)
            # Ao remover uma linha, os índices seguintes podem mudar; limpa toda revisão deste arquivo.
            meta = self.load_meta(equipment_key, lot)
            refs = [x for x in list(meta.get("registros_suspeitos_sincronizacao") or [])
                    if str(x.get("arquivo") or "") != path.name]
            meta["registros_suspeitos_sincronizacao"] = refs
            if not refs:
                meta.pop("reaberto_por_conflito", None)
            atomic_json_write(self.meta_path(equipment_key, lot), meta)
            return True

    def accept_sync_review(self, equipment_key: str, lot: str, source_file: str, record_index: int, actor: str):
        if self.is_finalized(equipment_key, lot):
            raise ValueError("Reabra o lote antes de aceitar um registro sincronizado após a finalização.")
        self._clear_sync_review_ref(equipment_key, lot, source_file, record_index)
        history = self.lot_dir(equipment_key, lot) / "historico"
        history.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_aceite_sync_" + uuid.uuid4().hex[:8] + ".json"
        atomic_json_write(history / name, {
            "tipo": "ACEITE_REGISTRO_SINCRONIZADO",
            "aceito_em": now_iso(),
            "aceito_por": actor,
            "arquivo_envio": source_file,
            "indice": int(record_index),
        })
        self._mark_changed_after_export(equipment_key, lot)

    def reopen_after_sync_conflict(self, equipment_key: str, lot: str, actor: str):
        with self.lot_lock(equipment_key, lot):
            final_path = self.lot_dir(equipment_key, lot) / "finalizado.json"
            if not final_path.exists():
                raise ValueError("Este lote não está finalizado.")
            records = self.load_records(equipment_key, lot)
            integrity = self.finalization_integrity(equipment_key, lot, records)
            if not integrity.get("changed"):
                raise ValueError("Não existe alteração pós-finalização para reabrir.")
            final_data = read_json(final_path, {}) or {}
            suspects = []
            for r in integrity.get("suspect_records", []):
                suspects.append({
                    "arquivo": str(r.get("_arquivo_envio") or ""),
                    "indice": int(r.get("_indice_envio", 0) or 0),
                })
            history = self.lot_dir(equipment_key, lot) / "historico"
            history.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_reabertura_sync_" + uuid.uuid4().hex[:8] + ".json"
            atomic_json_write(history / name, {
                "tipo": "REABERTURA_POR_CONFLITO_SINCRONIZACAO",
                "reaberto_em": now_iso(),
                "reaberto_por": actor,
                "finalizacao_anterior": final_data,
                "motivo": integrity.get("reason", ""),
                "registros_suspeitos": suspects,
            })
            meta = self.load_meta(equipment_key, lot)
            meta["dados_alterados_apos_exportacao"] = True
            meta["reaberto_por_conflito"] = True
            meta["registros_suspeitos_sincronizacao"] = suspects
            meta["ultima_alteracao_em"] = now_iso()
            atomic_json_write(self.meta_path(equipment_key, lot), meta)
            final_path.unlink(missing_ok=True)
'''
if marker_submit not in source:
    raise SystemExit("Ponto de inserção dos helpers não encontrado")
source = source.replace(marker_submit, "\n" + helpers + marker_submit, 1)

# Novos envios registram o PC de origem.
needle_payload = '''                "usuario": username,\n                "enviado_em": now_iso(),'''
replacement_payload = '''                "usuario": username,\n                "origem_pc": self.computer_name(),\n                "enviado_em": now_iso(),'''
if needle_payload not in source:
    raise SystemExit("Payload de envio não encontrado")
source = source.replace(needle_payload, replacement_payload, 1)

# Finalização guarda uma fotografia verificável do lote e bloqueia conflitos/revisões pendentes.
new_finalize = r'''    def finalize(self, equipment_key: str, lot: str, username: str):
        with self.lot_lock(equipment_key, lot):
            if self.is_finalized(equipment_key, lot):
                integrity = self.finalization_integrity(equipment_key, lot)
                if integrity.get("changed"):
                    raise ValueError(
                        "O lote recebeu ou teve dados alterados depois da finalização. "
                        "Abra o painel Conflitos para revisar e reabrir com segurança."
                    )
                return
            records = self.load_records(equipment_key, lot)
            count = len(records)
            meta = self.load_meta(equipment_key, lot)
            if count == 0:
                raise ValueError("O lote está vazio.")
            conflicts = self.conflicts_from_records(records)
            if conflicts:
                raise ValueError(
                    f"O lote possui {len(conflicts)} conflito(s) de SERIAL/ICCID. "
                    "Resolva os conflitos antes de finalizar."
                )
            review = self.sync_review_records(equipment_key, lot, records)
            if review:
                raise ValueError(
                    f"Existem {len(review)} registro(s) aguardando revisão de sincronização. "
                    "Revise-os no painel Conflitos antes de finalizar."
                )
            if (int(meta.get("ultima_exportacao_quantidade", -1)) != count or
                    bool(meta.get("dados_alterados_apos_exportacao"))):
                raise ValueError(
                    "O lote mudou desde a última exportação (ou ainda não foi exportado). "
                    "Exporte novamente antes de finalizar."
                )
            atomic_json_write(self.lot_dir(equipment_key, lot) / "finalizado.json", {
                "finalizado_em": now_iso(),
                "finalizado_por": username,
                "quantidade": count,
                "fingerprint": self.records_fingerprint(records),
                "assinaturas_envio": self.source_signatures(records),
            })
'''
sub_once(r'    def finalize\(self, equipment_key: str, lot: str, username: str\):.*?(?=\n    def list_lots\()', new_finalize, "finalize")

# Central passa a sinalizar conflito, revisão de sincronização e mudança pós-finalização.
new_list_lots = r'''    def list_lots(self, equipments: dict) -> list[LotInfo]:
        result = []
        base = self.root / "lotes"
        if not base.exists():
            return result
        for eqdir in base.iterdir():
            if not eqdir.is_dir():
                continue
            eqkey = eqdir.name
            eqcfg = equipments.get(eqkey, {})
            eqname = eqcfg.get("nome", eqkey)
            for ldir in eqdir.iterdir():
                if not ldir.is_dir():
                    continue
                lot = ldir.name
                records = self.load_records(eqkey, lot)
                meta = self.load_meta(eqkey, lot)
                finalized = self.is_finalized(eqkey, lot)
                last_exp = int(meta.get("ultima_exportacao_quantidade", 0) or 0)
                count = len(records)
                conflicts = self.conflicts_from_records(records)
                review = self.sync_review_records(eqkey, lot, records)
                integrity = self.finalization_integrity(eqkey, lot, records) if finalized else {"changed": False}
                post_changed = bool(integrity.get("changed"))

                if post_changed:
                    status = "CONFLITO PÓS-FINALIZAÇÃO"
                elif conflicts:
                    status = f"CONFLITO — {len(conflicts)}"
                elif review:
                    status = f"REVISÃO PÓS-SINCRONIZAÇÃO — {len(review)}"
                elif finalized:
                    status = "FINALIZADO"
                elif bool(meta.get("dados_alterados_apos_exportacao")):
                    status = "DADOS ALTERADOS APÓS EXPORTAÇÃO"
                elif last_exp and last_exp == count:
                    status = "EXPORTADO / ABERTO"
                elif last_exp and last_exp != count:
                    status = "DADOS ALTERADOS APÓS EXPORTAÇÃO"
                else:
                    status = "ABERTO"
                operators = sorted({str(r.get("OPERADORA", "")) for r in records if r.get("OPERADORA")})
                result.append(LotInfo(
                    eqkey, eqname, lot, count, operators, status, last_exp, finalized,
                    len(conflicts), post_changed, len(review)
                ))
        result.sort(key=lambda x: (x.finalized, x.equipment_name, x.lot), reverse=False)
        return result
'''
sub_once(r'    def list_lots\(self, equipments: dict\) -> list\[LotInfo\]:.*?(?=\n\nclass ExcelExporter:)', new_list_lots, "list_lots")

# -----------------------------------------------------------------------------
# Validação genérica para o painel de conflitos, sem depender do lote em bipagem.
# -----------------------------------------------------------------------------
central_marker = "\n    # ---------------- Central ----------------\n"
generic_validation = r'''
    def identify_operator_for_equipment(self, eq_key: str, iccid: str) -> str | None:
        cfg = self.equipments[eq_key]
        rules = sorted(cfg.get("operadoras_por_prefixo", []), key=lambda x: len(x.get("prefixo", "")), reverse=True)
        for item in rules:
            if iccid.startswith(str(item.get("prefixo", ""))):
                return str(item.get("operadora", "")).upper()
        return None

    def validate_field_for_equipment(self, eq_key: str, field: str, raw: str):
        cfg = self.equipments[eq_key]
        rule = cfg.get("validacoes", {}).get(field, {})
        value = raw.strip()
        if rule.get("maiusculo"):
            value = value.upper()
        typ = rule.get("tipo")
        if typ == "digitos" and not value.isdigit():
            return False, value, f"{field} deve conter somente números."
        if typ == "alfanumerico" and not re.fullmatch(r"[A-Za-z0-9]+", value or ""):
            return False, value, f"{field} deve conter somente letras e números."
        if field == "ICCID":
            op = self.identify_operator_for_equipment(eq_key, value)
            if not op:
                return False, value, "ICCID com prefixo de operadora não cadastrado."
            rules = cfg.get("operadoras_por_prefixo", [])
            item = next((x for x in rules if value.startswith(str(x.get("prefixo", ""))) and str(x.get("operadora", "")).upper() == op), None)
            expected = (item or {}).get("tamanho_iccid", rule.get("tamanho"))
            if expected and len(value) != int(expected):
                return False, value, f"ICCID da {op} deve ter exatamente {expected} dígitos."
        else:
            size = rule.get("tamanho")
            if size and len(value) != int(size):
                return False, value, f"{field} deve ter exatamente {size} caracteres."
        return True, value, ""
'''
if central_marker not in source:
    raise SystemExit("Marcador da Central não encontrado")
source = source.replace(central_marker, "\n" + generic_validation + central_marker, 1)

# Botão dedicado na Central.
old_toolbar = '        ttk.Button(toolbar, text="Finalizar lote", command=self.finalize_selected_lot).pack(side="left", padx=6)\n'
new_toolbar = old_toolbar + '        ttk.Button(toolbar, text="Conflitos", command=self.view_selected_conflicts).pack(side="left")\n'
if old_toolbar not in source:
    raise SystemExit("Toolbar da Central não encontrada")
source = source.replace(old_toolbar, new_toolbar, 1)

# Painel de conflitos: mostra duplicidades, usuário, PC e permite resolver sem apagar automaticamente.
marker_export = "\n    def export_selected_lot(self):\n"
conflict_ui = r'''
    def view_selected_conflicts(self):
        info = self.selected_lot_info()
        if not info:
            return

        win = tk.Toplevel(self)
        win.title(f"Conflitos — {info.equipment_name} — Lote {info.lot}")
        win.geometry("1220x620")
        win.minsize(1000, 520)

        header_var = tk.StringVar()
        detail_var = tk.StringVar()
        ttk.Label(win, textvariable=header_var, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Label(win, textvariable=detail_var, wraplength=1150).pack(anchor="w", padx=12, pady=(0, 10))

        cols = ("MOTIVO", "SERIAL", "ICCID", "OPERADORA", "USUARIO", "PC", "ENVIADO")
        table = ttk.Treeview(win, columns=cols, show="headings", height=20)
        widths = {"MOTIVO":260, "SERIAL":130, "ICCID":210, "OPERADORA":110, "USUARIO":130, "PC":150, "ENVIADO":180}
        for c in cols:
            table.heading(c, text=c)
            table.column(c, width=widths[c], anchor="center")
        table.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        edit_btn = ttk.Button(buttons, text="Editar registro")
        delete_btn = ttk.Button(buttons, text="Excluir registro")
        accept_btn = ttk.Button(buttons, text="Aceitar sincronizado")
        reopen_btn = ttk.Button(buttons, text="Reabrir para corrigir")
        edit_btn.pack(side="left")
        delete_btn.pack(side="left", padx=6)
        accept_btn.pack(side="left")
        reopen_btn.pack(side="right")

        row_map = {}
        current_state = {}

        def refresh_view():
            records = self.store.load_records(info.equipment_key, info.lot)
            conflicts = self.store.conflicts_from_records(records)
            finalized = self.store.is_finalized(info.equipment_key, info.lot)
            integrity = self.store.finalization_integrity(info.equipment_key, info.lot, records) if finalized else {"changed": False, "suspect_records": []}
            review = self.store.sync_review_records(info.equipment_key, info.lot, records)
            current_state.clear()
            current_state.update({"records": records, "conflicts": conflicts, "finalized": finalized, "integrity": integrity, "review": review})

            rows = {}
            def add_reason(rec, reason):
                key = (str(rec.get("_arquivo_envio") or ""), int(rec.get("_indice_envio", 0) or 0))
                if not key[0]:
                    return
                item = rows.setdefault(key, {"rec": rec, "reasons": []})
                if reason not in item["reasons"]:
                    item["reasons"].append(reason)

            for conflict in conflicts:
                reason = f"{conflict['campo']} duplicado: {conflict['valor']}"
                for rec in conflict.get("registros", []):
                    add_reason(rec, reason)
            for rec in integrity.get("suspect_records", []):
                add_reason(rec, "Alterado/chegou após finalização")
            for rec in review:
                add_reason(rec, "Aguardando revisão de sincronização")

            table.delete(*table.get_children())
            row_map.clear()
            for n, (_key, item) in enumerate(sorted(rows.items(), key=lambda x: (x[0][0], x[0][1]))):
                rec = item["rec"]
                iid = str(n)
                row_map[iid] = rec
                table.insert("", "end", iid=iid, values=(
                    " | ".join(item["reasons"]), rec.get("SERIAL"), rec.get("ICCID"), rec.get("OPERADORA"),
                    rec.get("_usuario") or "—", rec.get("_origem_pc") or "—", rec.get("_enviado_em") or "—"
                ))

            header_var.set(f"{info.equipment_name} — Lote {info.lot} — {len(conflicts)} conflito(s)")
            if finalized and integrity.get("changed"):
                detail_var.set("ATENÇÃO: o lote mudou depois de ter sido finalizado. " + str(integrity.get("reason") or ""))
                reopen_btn.config(state="normal")
                edit_btn.config(state="disabled")
                delete_btn.config(state="disabled")
                accept_btn.config(state="disabled")
            else:
                detail_var.set(
                    "Selecione o registro incorreto para editar ou excluir. Nada é removido automaticamente. "
                    "Registros sincronizados após uma reabertura também podem ser aceitos explicitamente."
                )
                reopen_btn.config(state="disabled")
                edit_btn.config(state="normal" if rows else "disabled")
                delete_btn.config(state="normal" if rows else "disabled")
                accept_btn.config(state="normal" if review else "disabled")

            if not rows and not (finalized and integrity.get("changed")):
                detail_var.set("Nenhum conflito ou registro pendente de revisão foi encontrado neste lote.")

        def selected_record():
            sel = table.selection()
            if not sel:
                messagebox.showinfo("Conflitos", "Selecione um registro.", parent=win)
                return None
            return row_map.get(sel[0])

        def edit_selected():
            rec = selected_record()
            if not rec:
                return
            if current_state.get("finalized"):
                messagebox.showerror("Conflitos", "Reabra o lote antes de editar.", parent=win)
                return
            edit = tk.Toplevel(win)
            edit.title("Corrigir registro em conflito")
            edit.resizable(False, False)
            edit.transient(win)
            edit.grab_set()
            vars_ = {k: tk.StringVar(value=str(rec.get(k) or "")) for k in ("SERIAL", "ICCID", "SENHA")}
            entries = {}
            ttk.Label(edit, text="Corrigir registro", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 10), sticky="w")
            for row, field in enumerate(("SERIAL", "ICCID", "SENHA"), start=1):
                ttk.Label(edit, text=field).grid(row=row, column=0, padx=(18, 10), pady=5, sticky="e")
                ent = ttk.Entry(edit, textvariable=vars_[field], width=32, font=("Consolas", 11))
                ent.grid(row=row, column=1, padx=(0, 18), pady=5)
                entries[field] = ent
            op_var = tk.StringVar(value=str(rec.get("OPERADORA") or "—"))
            ttk.Label(edit, text="OPERADORA").grid(row=4, column=0, padx=(18, 10), pady=5, sticky="e")
            ttk.Label(edit, textvariable=op_var, font=("Segoe UI", 10, "bold")).grid(row=4, column=1, padx=(0, 18), pady=5, sticky="w")
            msg_var = tk.StringVar(value="A operadora é calculada pelo ICCID.")
            ttk.Label(edit, textvariable=msg_var, wraplength=420).grid(row=5, column=0, columnspan=2, padx=18, pady=(5, 10), sticky="w")
            vars_["ICCID"].trace_add("write", lambda *_: op_var.set(self.identify_operator_for_equipment(info.equipment_key, vars_["ICCID"].get().strip()) or "—"))

            def save():
                corrected = {}
                for field in ("SERIAL", "ICCID", "SENHA"):
                    ok, value, error = self.validate_field_for_equipment(info.equipment_key, field, vars_[field].get())
                    if not ok:
                        msg_var.set("ERRO: " + error)
                        self.bell()
                        entries[field].focus_set()
                        return
                    corrected[field] = value
                corrected["OPERADORA"] = self.identify_operator_for_equipment(info.equipment_key, corrected["ICCID"])
                try:
                    changed = self.store.edit_record_by_source(
                        info.equipment_key, info.lot, rec.get("_arquivo_envio", ""),
                        int(rec.get("_indice_envio", 0) or 0), corrected, self.username
                    )
                except (ValueError, TimeoutError, OSError) as exc:
                    msg_var.set("ERRO: " + str(exc))
                    return
                if not changed:
                    msg_var.set("ERRO: o registro não foi encontrado. Aguarde a sincronização e tente novamente.")
                    return
                edit.destroy()
                self.refresh_lots()
                refresh_view()

            bar = ttk.Frame(edit)
            bar.grid(row=6, column=0, columnspan=2, padx=18, pady=(4, 18), sticky="e")
            ttk.Button(bar, text="Cancelar", command=edit.destroy).pack(side="left", padx=(0, 8))
            ttk.Button(bar, text="Salvar correção", command=save).pack(side="left")
            edit.wait_visibility()
            entries["SERIAL"].focus_force()

        def delete_selected():
            rec = selected_record()
            if not rec:
                return
            if not messagebox.askyesno(
                "Excluir registro",
                f"Excluir este registro do lote?\n\nSERIAL: {rec.get('SERIAL')}\nICCID: {rec.get('ICCID')}\nUsuário: {rec.get('_usuario') or '—'}\nPC: {rec.get('_origem_pc') or '—'}",
                parent=win,
            ):
                return
            try:
                removed = self.store.delete_record_by_source(
                    info.equipment_key, info.lot, rec.get("_arquivo_envio", ""),
                    int(rec.get("_indice_envio", 0) or 0), self.username
                )
            except (ValueError, TimeoutError, OSError) as exc:
                messagebox.showerror("Conflitos", str(exc), parent=win)
                return
            if not removed:
                messagebox.showerror("Conflitos", "O registro não foi encontrado.", parent=win)
                return
            self.refresh_lots()
            refresh_view()

        def accept_selected():
            rec = selected_record()
            if not rec:
                return
            try:
                self.store.accept_sync_review(
                    info.equipment_key, info.lot, rec.get("_arquivo_envio", ""),
                    int(rec.get("_indice_envio", 0) or 0), self.username
                )
            except (ValueError, TimeoutError, OSError) as exc:
                messagebox.showerror("Conflitos", str(exc), parent=win)
                return
            self.refresh_lots()
            refresh_view()

        def reopen():
            if not messagebox.askyesno(
                "Reabrir lote",
                "Este lote recebeu ou teve dados alterados depois da finalização.\n\n"
                "Reabrir permitirá revisar os registros. Depois será obrigatório exportar novamente e finalizar de novo.\n\nDeseja continuar?",
                parent=win,
            ):
                return
            try:
                self.store.reopen_after_sync_conflict(info.equipment_key, info.lot, self.username)
            except (ValueError, TimeoutError, OSError) as exc:
                messagebox.showerror("Conflitos", str(exc), parent=win)
                return
            self.refresh_lots()
            refresh_view()

        edit_btn.config(command=edit_selected)
        delete_btn.config(command=delete_selected)
        accept_btn.config(command=accept_selected)
        reopen_btn.config(command=reopen)
        table.bind("<Double-1>", lambda _e: edit_selected())
        refresh_view()
'''
if marker_export not in source:
    raise SystemExit("Ponto de inserção do painel de conflitos não encontrado")
source = source.replace(marker_export, "\n" + conflict_ui + marker_export, 1)

# Exportação fica bloqueada por conflito, revisão pendente ou alteração pós-finalização.
new_export_start = r'''    def export_selected_lot(self):
        info = self.selected_lot_info()
        if not info:
            return
        records = self.store.load_records(info.equipment_key, info.lot)
        if not records:
            messagebox.showwarning("Exportar", "O lote está vazio.")
            return
        conflicts = self.store.conflicts_from_records(records)
        if conflicts:
            messagebox.showerror(
                "Exportação bloqueada",
                f"O lote possui {len(conflicts)} conflito(s) de SERIAL/ICCID.\n\nAbra Conflitos e resolva antes de exportar."
            )
            return
        if self.store.is_finalized(info.equipment_key, info.lot):
            integrity = self.store.finalization_integrity(info.equipment_key, info.lot, records)
            if integrity.get("changed"):
                messagebox.showerror(
                    "Exportação bloqueada",
                    "O lote mudou depois da finalização. Abra Conflitos e use Reabrir para corrigir antes de exportar novamente."
                )
                return
        review = self.store.sync_review_records(info.equipment_key, info.lot, records)
        if review:
            messagebox.showerror(
                "Exportação bloqueada",
                f"Existem {len(review)} registro(s) aguardando revisão de sincronização.\n\nAbra Conflitos e revise-os antes de exportar."
            )
            return
'''
# Preserva o restante do método antigo a partir da escolha da pasta.
pattern_export_prefix = r'    def export_selected_lot\(self\):.*?        destination = filedialog\.askdirectory\(title="Escolha a pasta onde serão salvas as planilhas"\)'
replacement_export_prefix = new_export_start + '        destination = filedialog.askdirectory(title="Escolha a pasta onde serão salvas as planilhas")'
sub_once(pattern_export_prefix, replacement_export_prefix, "bloqueios de exportação")

# Atualização em segundo plano também avisa conflito sem repintar a tela.
new_poll = r'''    def _poll_live_counts(self):
        if self.current_eq_key and self.current_lot and not self._live_refresh_busy:
            eq_key = self.current_eq_key
            lot = self.current_lot
            username = self.username
            self._live_refresh_busy = True

            def worker():
                error = None
                user_count = total_count = 0
                warning = ""
                try:
                    records = self.store.load_records(eq_key, lot)
                    wanted = str(username or "").strip().casefold()
                    user_count = sum(1 for r in records if str(r.get("_usuario") or "").strip().casefold() == wanted)
                    total_count = len(records)
                    conflicts = self.store.conflicts_from_records(records)
                    finalized = self.store.is_finalized(eq_key, lot)
                    if finalized:
                        integrity = self.store.finalization_integrity(eq_key, lot, records)
                        if integrity.get("changed"):
                            warning = "ATENÇÃO: dados chegaram ou mudaram após a finalização. Abra a Central > Conflitos."
                    if not warning and conflicts:
                        warning = f"ATENÇÃO: {len(conflicts)} conflito(s) detectado(s). Abra a Central > Conflitos."
                    if not warning:
                        review = self.store.sync_review_records(eq_key, lot, records)
                        if review:
                            warning = f"ATENÇÃO: {len(review)} registro(s) aguardando revisão de sincronização."
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
                    text = warning or "Atualização automática ativa — verifica alterações a cada 2 segundos"
                    if self.sync_status_var.get() != text:
                        self.sync_status_var.set(text)

                try:
                    self.after(0, apply_result)
                except tk.TclError:
                    pass

            threading.Thread(target=worker, daemon=True).start()
        self.after(2000, self._poll_live_counts)
'''
sub_once(r'    def _poll_live_counts\(self\):.*?(?=\n    def start_lot\()', new_poll, "poll de conflitos")

# Informação da tela de Configurações.
needle_info = '        ttk.Label(info, text="Correções: peças da sessão podem ser editadas; toda edição é validada, registrada no histórico e invalida exportação anterior.").pack(anchor="w", pady=3)\n'
replacement_info = needle_info + '        ttk.Label(info, text="OneDrive: conflitos sincronizados são detectados; exportação/finalização ficam bloqueadas até a revisão.").pack(anchor="w", pady=3)\n'
if needle_info not in source:
    raise SystemExit("Texto de configuração da v0.2.6 não encontrado")
source = source.replace(needle_info, replacement_info, 1)

required = [
    'APP_VERSION = "0.2.7"',
    'def conflicts_from_records',
    'CONFLITO PÓS-FINALIZAÇÃO',
    'def view_selected_conflicts',
    'Reabrir para corrigir',
    'origem_pc',
    'assinaturas_envio',
    'registros_suspeitos_sincronizacao',
    'Exportação bloqueada',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.2.7 gerado com sucesso")
