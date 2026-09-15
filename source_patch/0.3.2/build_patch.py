from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.3.1" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.3.1 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.3.1"', 'APP_VERSION = "0.3.2"', 1)
if 'APP_VERSION = "0.3.2"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# Etapa 7 — catálogo compartilhado de equipamentos, operadoras e modelos.
marker = "    def user_path(self, username: str) -> Path:\n"
helpers = r'''    def equipment_catalog_path(self) -> Path:
        return self.root / "configuracao" / "equipamentos.json"

    def load_equipment_catalog(self, defaults: dict) -> dict:
        path = self.equipment_catalog_path()
        custom = read_json(path, None)
        if isinstance(custom, dict) and custom:
            valid = {k: v for k, v in custom.items() if isinstance(k, str) and isinstance(v, dict)}
            if valid:
                return valid
        return json.loads(json.dumps(defaults or {}, ensure_ascii=False))

    def save_equipment_catalog(self, equipments: dict) -> None:
        if not isinstance(equipments, dict) or not equipments:
            raise ValueError("O catálogo de equipamentos não pode ficar vazio.")
        atomic_json_write(self.equipment_catalog_path(), equipments)

    def shared_template_path(self, rel: str) -> Path:
        text = str(rel or "").strip()
        prefix = "shared://"
        if text.lower().startswith(prefix):
            return self.root / text[len(prefix):].replace("/", os.sep)
        return Path(text)

'''
if marker not in source:
    raise SystemExit("Ponto de inserção do catálogo não encontrado")
source = source.replace(marker, helpers + marker, 1)

needle_load = '        self.equipments = read_json(self.base_dir / "config" / "equipamentos.json", {}) or {}\n'
replacement_load = needle_load + '        self.bundled_equipments = json.loads(json.dumps(self.equipments, ensure_ascii=False))\n'
if needle_load not in source:
    raise SystemExit("Carga de equipamentos não encontrada")
source = source.replace(needle_load, replacement_load, 1)

needle_store = '        self.store = DataStore(self.shared_path)\n'
replacement_store = needle_store + '        self.equipments = self.store.load_equipment_catalog(self.bundled_equipments)\n'
if needle_store not in source:
    raise SystemExit("Criação do DataStore não encontrada")
source = source.replace(needle_store, replacement_store, 1)

old_ctor = r'''    def __init__(self, base_dir: Path, equipment_cfg: dict):
        self.base_dir = base_dir
        self.cfg = equipment_cfg

    def _template(self, rel: str) -> Path:
        p = self.base_dir / rel
        if not p.exists():
            raise FileNotFoundError(f"Modelo não encontrado: {p}")
        return p
'''
new_ctor = r'''    def __init__(self, base_dir: Path, equipment_cfg: dict, shared_dir: Path | None = None):
        self.base_dir = base_dir
        self.cfg = equipment_cfg
        self.shared_dir = Path(shared_dir) if shared_dir else None

    def _template(self, rel: str) -> Path:
        text = str(rel or "").strip()
        if text.lower().startswith("shared://"):
            if self.shared_dir is None:
                raise FileNotFoundError("Pasta compartilhada não informada para resolver o modelo.")
            p = self.shared_dir / text[len("shared://"):].replace("/", os.sep)
        else:
            candidate = Path(text)
            p = candidate if candidate.is_absolute() else self.base_dir / candidate
        if not p.exists():
            raise FileNotFoundError(f"Modelo não encontrado: {p}")
        return p
'''
if old_ctor not in source:
    raise SystemExit("Construtor do ExcelExporter não encontrado")
source = source.replace(old_ctor, new_ctor, 1)
source = source.replace(
    'ExcelExporter(self.base_dir, self.equipments[info.equipment_key])',
    'ExcelExporter(self.base_dir, self.equipments[info.equipment_key], self.shared_path)',
)

marker_preflight = "    def _export_preflight(self, info: LotInfo) -> dict:\n"
resolver = r'''    def _resolve_template_path(self, rel: str) -> Path:
        text = str(rel or "").strip()
        if text.lower().startswith("shared://"):
            return self.shared_path / text[len("shared://"):].replace("/", os.sep)
        candidate = Path(text)
        return candidate if candidate.is_absolute() else self.base_dir / candidate

'''
if marker_preflight not in source:
    raise SystemExit("Pré-exportação não encontrada")
source = source.replace(marker_preflight, resolver + marker_preflight, 1)
source = source.replace('nf_path = self.base_dir / nf_rel if nf_rel else None', 'nf_path = self._resolve_template_path(nf_rel) if nf_rel else None')
source = source.replace('path = self.base_dir / rel if rel else None', 'path = self._resolve_template_path(rel) if rel else None')

settings_marker = "    # ---------------- Configurações ----------------\n"
catalog_methods = r'''    # ---------------- Catálogo de equipamentos / operadoras ----------------
    @staticmethod
    def _equipment_key_from_label(name: str) -> str:
        text = unicodedata.normalize("NFD", str(name or "").upper())
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return re.sub(r"[^A-Z0-9]+", "_", text).strip("_") or "EQUIPAMENTO"

    def _copy_catalog_template(self, equipment_key: str, source_file: str, kind: str, operator: str = "") -> str:
        src = Path(source_file)
        if not src.exists() or not src.is_file():
            raise FileNotFoundError("O arquivo selecionado não existe.")
        if src.suffix.lower() not in (".xls", ".xlsx", ".xlsm", ".xlsb"):
            raise ValueError("Selecione um arquivo do Excel (.xls, .xlsx, .xlsm ou .xlsb).")
        folder = self.shared_path / "catalogo_modelos" / safe_name(equipment_key)
        folder.mkdir(parents=True, exist_ok=True)
        if kind == "nf":
            filename = "modelo_nf" + src.suffix.lower()
        else:
            filename = f"modelo_importacao_{safe_name(operator).upper()}" + src.suffix.lower()
        dest = folder / filename
        shutil.copy2(src, dest)
        rel = dest.relative_to(self.shared_path).as_posix()
        return "shared://" + rel

    def _refresh_equipment_widgets(self):
        names = [cfg.get("nome", key) for key, cfg in self.equipments.items()]
        if hasattr(self, "eq_combo"):
            current = self.eq_var.get()
            self.eq_combo["values"] = names
            if current not in names:
                self.eq_var.set("")
                self.lot_var.set("")
                if hasattr(self, "open_lots_var"):
                    self.open_lots_var.set("Selecione um equipamento para ver os lotes abertos.")
        if hasattr(self, "central_equipment_combo"):
            self.central_equipment_combo["values"] = ["Todos", *sorted(names, key=str.casefold)]
        if hasattr(self, "lots_tree"):
            self.refresh_lots()

    def reload_shared_catalog(self, show_message: bool = True):
        try:
            loaded = self.store.load_equipment_catalog(self.bundled_equipments)
            if not loaded:
                raise ValueError("O catálogo compartilhado está vazio.")
            self.equipments = loaded
            self._refresh_equipment_widgets()
            if show_message:
                messagebox.showinfo(
                    "Cadastros",
                    "Cadastros compartilhados recarregados.\n\n"
                    "Use esta opção nos outros PCs depois que alguém alterar equipamentos, operadoras ou modelos.",
                )
        except Exception as exc:
            messagebox.showerror("Cadastros", f"Não foi possível recarregar os cadastros:\n{exc}")

    def manage_equipment_catalog(self):
        win = tk.Toplevel(self)
        win.title("Equipamentos, operadoras e modelos")
        win.geometry("980x720")
        win.minsize(880, 620)
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Equipamentos, operadoras e modelos", font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=16, pady=(16, 3)
        )
        ttk.Label(
            win,
            text=(
                "O catálogo é salvo em DADOS_COMPARTILHADOS. Um lote pode conter várias operadoras; "
                "na exportação o Mestre/NF usa o lote inteiro e a importação é separada automaticamente por operadora."
            ),
            wraplength=930,
        ).pack(anchor="w", padx=16, pady=(0, 10))

        top = ttk.Frame(win)
        top.pack(fill="x", padx=16, pady=(0, 10))
        ttk.Label(top, text="Equipamento:").pack(side="left")
        eq_var = tk.StringVar()
        eq_combo = ttk.Combobox(top, textvariable=eq_var, state="readonly", width=34)
        eq_combo.pack(side="left", padx=(6, 8))
        ttk.Button(top, text="Novo equipamento", command=lambda: new_equipment()).pack(side="left")
        ttk.Button(top, text="Recarregar compartilhado", command=lambda: reload_here()).pack(side="right")

        form = ttk.LabelFrame(win, text="Configuração do equipamento", padding=10)
        form.pack(fill="x", padx=16, pady=(0, 10))
        form.columnconfigure(1, weight=1)
        name_var = tk.StringVar()
        serial_on = tk.BooleanVar(value=True)
        iccid_on = tk.BooleanVar(value=True)
        password_on = tk.BooleanVar(value=True)
        serial_size = tk.StringVar(value="10")
        password_size = tk.StringVar(value="10")
        nf_var = tk.StringVar()
        key_var = tk.StringVar()

        ttk.Label(form, text="Nome:").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        ttk.Entry(form, textvariable=name_var).grid(row=0, column=1, columnspan=4, sticky="ew", pady=4)
        ttk.Label(form, text="Chave interna:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        ttk.Label(form, textvariable=key_var, font=("Consolas", 9)).grid(row=1, column=1, columnspan=4, sticky="w", pady=4)
        ttk.Label(form, text="Campos:").grid(row=2, column=0, sticky="ne", padx=(0, 6), pady=4)
        ttk.Checkbutton(form, text="SERIAL", variable=serial_on).grid(row=2, column=1, sticky="w")
        ttk.Label(form, text="Tamanho:").grid(row=2, column=2, sticky="e")
        ttk.Entry(form, textvariable=serial_size, width=5).grid(row=2, column=3, sticky="w", padx=(4, 14))
        ttk.Checkbutton(form, text="ICCID (obrigatório)", variable=iccid_on, state="disabled").grid(row=2, column=4, sticky="w")
        ttk.Checkbutton(form, text="SENHA", variable=password_on).grid(row=3, column=1, sticky="w")
        ttk.Label(form, text="Tamanho:").grid(row=3, column=2, sticky="e")
        ttk.Entry(form, textvariable=password_size, width=5).grid(row=3, column=3, sticky="w", padx=(4, 14))
        ttk.Label(form, text="Modelo Mestre/NF:").grid(row=4, column=0, sticky="e", padx=(0, 6), pady=(8, 4))
        ttk.Label(form, textvariable=nf_var, wraplength=610).grid(row=4, column=1, columnspan=3, sticky="w", pady=(8, 4))
        ttk.Button(form, text="Escolher arquivo...", command=lambda: choose_nf()).grid(row=4, column=4, sticky="e", pady=(8, 4))

        ops_box = ttk.LabelFrame(win, text="Operadoras aceitas neste equipamento", padding=10)
        ops_box.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        ttk.Label(
            ops_box,
            text="Cada peça identifica sua própria operadora pelo prefixo do ICCID. Por isso VIVO, CLARO, TIM etc. podem coexistir no mesmo lote.",
            wraplength=900,
        ).pack(anchor="w", pady=(0, 7))
        op_cols = ("operadora", "prefixo", "tamanho", "modelo")
        op_tree = ttk.Treeview(ops_box, columns=op_cols, show="headings", height=10, selectmode="browse")
        headers = {"operadora":"OPERADORA", "prefixo":"PREFIXO ICCID", "tamanho":"TAMANHO", "modelo":"MODELO DE IMPORTAÇÃO"}
        widths = {"operadora":150, "prefixo":170, "tamanho":100, "modelo":410}
        for col in op_cols:
            op_tree.heading(col, text=headers[col])
            op_tree.column(col, width=widths[col], anchor="center")
        op_tree.pack(fill="both", expand=True)

        op_actions = ttk.Frame(ops_box)
        op_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(op_actions, text="Adicionar operadora", command=lambda: edit_operator(None)).pack(side="left")
        ttk.Button(op_actions, text="Editar operadora", command=lambda: edit_selected_operator()).pack(side="left", padx=(6, 0))
        ttk.Button(op_actions, text="Modelo de importação...", command=lambda: choose_operator_model()).pack(side="left", padx=(6, 0))
        ttk.Button(op_actions, text="Remover operadora", command=lambda: remove_operator()).pack(side="left", padx=(6, 0))

        status_var = tk.StringVar(value="")
        ttk.Label(win, textvariable=status_var, wraplength=930).pack(anchor="w", padx=16, pady=(0, 6))
        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(bottom, text="Fechar", command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Salvar equipamento", command=lambda: save_equipment()).pack(side="right", padx=(0, 8))

        current_key = {"value": None}

        def equipment_labels():
            return [cfg.get("nome", key) for key, cfg in self.equipments.items()]

        def key_from_display(display: str):
            for key, cfg in self.equipments.items():
                if cfg.get("nome", key) == display:
                    return key
            return None

        def refresh_combo(prefer_key=None):
            labels = equipment_labels()
            eq_combo["values"] = labels
            if prefer_key and prefer_key in self.equipments:
                eq_var.set(self.equipments[prefer_key].get("nome", prefer_key))
            elif labels:
                eq_var.set(labels[0])
            else:
                eq_var.set("")

        def selected_cfg():
            key = current_key["value"]
            return self.equipments.get(key) if key else None

        def refresh_operators():
            op_tree.delete(*op_tree.get_children())
            cfg = selected_cfg() or {}
            rules = cfg.get("operadoras_por_prefixo", []) or []
            templates = (((cfg.get("exportacoes") or {}).get("importacao") or {}).get("templates_por_operadora") or {})
            for idx, rule in enumerate(rules):
                op = str(rule.get("operadora") or "").upper()
                rel = str(templates.get(op) or "").strip()
                model = Path(rel).name if rel else "NÃO CONFIGURADO"
                op_tree.insert("", "end", iid=str(idx), values=(op, rule.get("prefixo", ""), rule.get("tamanho_iccid", ""), model))

        def load_equipment(*_):
            key = key_from_display(eq_var.get())
            if not key:
                return
            current_key["value"] = key
            cfg = self.equipments[key]
            key_var.set(key)
            name_var.set(str(cfg.get("nome") or key))
            fields = list(cfg.get("campos") or ["SERIAL", "ICCID", "SENHA"])
            serial_on.set("SERIAL" in fields)
            iccid_on.set(True)
            password_on.set("SENHA" in fields)
            validations = cfg.get("validacoes") or {}
            serial_size.set(str((validations.get("SERIAL") or {}).get("tamanho", 10)))
            password_size.set(str((validations.get("SENHA") or {}).get("tamanho", 10)))
            nf_rel = str((((cfg.get("exportacoes") or {}).get("nf") or {}).get("template") or ""))
            nf_var.set(nf_rel or "NÃO CONFIGURADO")
            refresh_operators()
            status_var.set("")

        def simple_text_dialog(parent, title, label, initial=""):
            dlg = tk.Toplevel(parent)
            dlg.title(title)
            dlg.resizable(False, False)
            dlg.transient(parent)
            dlg.grab_set()
            value = {"result": None}
            var = tk.StringVar(value=initial)
            ttk.Label(dlg, text=label).grid(row=0, column=0, padx=16, pady=(16, 6), sticky="w")
            ent = ttk.Entry(dlg, textvariable=var, width=36)
            ent.grid(row=1, column=0, padx=16, pady=(0, 10))
            row = ttk.Frame(dlg)
            row.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="e")
            def accept(*_):
                value["result"] = var.get()
                dlg.destroy()
            ttk.Button(row, text="Cancelar", command=dlg.destroy).pack(side="left", padx=(0, 6))
            ttk.Button(row, text="OK", command=accept).pack(side="left")
            ent.bind("<Return>", accept)
            dlg.wait_visibility()
            ent.focus_force()
            parent.wait_window(dlg)
            return value["result"]

        def new_equipment():
            name = simple_text_dialog(win, "Novo equipamento", "Nome do equipamento:")
            if name is None:
                return
            clean = re.sub(r"\s+", " ", name.strip())
            if len(clean) < 2:
                messagebox.showwarning("Novo equipamento", "Informe um nome válido.", parent=win)
                return
            if any(str(cfg.get("nome") or "").casefold() == clean.casefold() for cfg in self.equipments.values()):
                messagebox.showwarning("Novo equipamento", "Já existe um equipamento com esse nome.", parent=win)
                return
            base_key = self._equipment_key_from_label(clean)
            key = base_key
            n = 2
            while key in self.equipments:
                key = f"{base_key}_{n}"
                n += 1
            self.equipments[key] = {
                "nome": clean,
                "campos": ["SERIAL", "ICCID", "SENHA"],
                "validacoes": {
                    "SERIAL": {"tipo": "alfanumerico", "tamanho": 10, "maiusculo": True},
                    "ICCID": {"tipo": "digitos", "tamanho": 20},
                    "SENHA": {"tipo": "alfanumerico", "tamanho": 10, "maiusculo": True},
                },
                "operadoras_por_prefixo": [],
                "exportacoes": {
                    "nf": {"template": "", "nome_saida": clean + " - Lote {lote} (NF).xlsx", "cabecalhos": ["SERIAL", "ICCID", "OPERADORA", "SENHA"], "limpar_celulas": []},
                    "importacao": {"nome_saida": clean + " - Lote {lote} - Importação de chip ({operadora}).xls", "templates_por_operadora": {}},
                },
            }
            self.store.save_equipment_catalog(self.equipments)
            refresh_combo(key)
            load_equipment()
            self._refresh_equipment_widgets()
            status_var.set("Novo equipamento criado no catálogo compartilhado. Configure as operadoras e os modelos.")

        def choose_nf():
            key = current_key["value"]
            if not key:
                return
            path = filedialog.askopenfilename(parent=win, title="Selecione o modelo Mestre/NF", filetypes=[("Arquivos do Excel", "*.xls *.xlsx *.xlsm *.xlsb"), ("Todos os arquivos", "*.*")])
            if not path:
                return
            try:
                rel = self._copy_catalog_template(key, path, "nf")
            except Exception as exc:
                messagebox.showerror("Modelo Mestre/NF", str(exc), parent=win)
                return
            cfg = self.equipments[key]
            cfg.setdefault("exportacoes", {}).setdefault("nf", {})["template"] = rel
            nf_var.set(rel)
            self.store.save_equipment_catalog(self.equipments)
            status_var.set("Modelo Mestre/NF copiado para DADOS_COMPARTILHADOS e salvo.")

        def save_equipment():
            key = current_key["value"]
            if not key or key not in self.equipments:
                return
            clean = re.sub(r"\s+", " ", name_var.get().strip())
            if len(clean) < 2:
                messagebox.showwarning("Equipamento", "Informe um nome válido.", parent=win)
                return
            try:
                s_size = int(serial_size.get()) if serial_on.get() else 10
                p_size = int(password_size.get()) if password_on.get() else 10
                if not (1 <= s_size <= 100 and 1 <= p_size <= 100):
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Equipamento", "Os tamanhos dos campos devem ser números entre 1 e 100.", parent=win)
                return
            for other_key, other in self.equipments.items():
                if other_key != key and str(other.get("nome") or "").casefold() == clean.casefold():
                    messagebox.showwarning("Equipamento", "Já existe outro equipamento com esse nome.", parent=win)
                    return
            cfg = self.equipments[key]
            cfg["nome"] = clean
            fields = []
            if serial_on.get():
                fields.append("SERIAL")
            fields.append("ICCID")
            if password_on.get():
                fields.append("SENHA")
            cfg["campos"] = fields
            validations = cfg.setdefault("validacoes", {})
            validations["ICCID"] = {"tipo": "digitos", "tamanho": 20}
            validations["SERIAL"] = {"tipo": "alfanumerico", "tamanho": s_size, "maiusculo": True}
            validations["SENHA"] = {"tipo": "alfanumerico", "tamanho": p_size, "maiusculo": True}
            exp = cfg.setdefault("exportacoes", {})
            nf = exp.setdefault("nf", {})
            nf.setdefault("cabecalhos", ["SERIAL", "ICCID", "OPERADORA", "SENHA"])
            nf.setdefault("limpar_celulas", [])
            nf.setdefault("nome_saida", clean + " - Lote {lote} (NF).xlsx")
            imp = exp.setdefault("importacao", {})
            imp.setdefault("templates_por_operadora", {})
            imp.setdefault("nome_saida", clean + " - Lote {lote} - Importação de chip ({operadora}).xls")
            self.store.save_equipment_catalog(self.equipments)
            refresh_combo(key)
            load_equipment()
            self._refresh_equipment_widgets()
            status_var.set("Equipamento salvo no catálogo compartilhado.")

        def selected_operator_index():
            sel = op_tree.selection()
            if not sel:
                messagebox.showinfo("Operadoras", "Selecione uma operadora.", parent=win)
                return None
            try:
                return int(sel[0])
            except ValueError:
                return None

        def edit_selected_operator():
            idx = selected_operator_index()
            if idx is not None:
                edit_operator(idx)

        def edit_operator(index):
            cfg = selected_cfg()
            if cfg is None:
                return
            rules = cfg.setdefault("operadoras_por_prefixo", [])
            original = dict(rules[index]) if index is not None and 0 <= index < len(rules) else {}
            dlg = tk.Toplevel(win)
            dlg.title("Editar operadora" if original else "Adicionar operadora")
            dlg.resizable(False, False)
            dlg.transient(win)
            dlg.grab_set()
            op_v = tk.StringVar(value=str(original.get("operadora") or ""))
            prefix_v = tk.StringVar(value=str(original.get("prefixo") or ""))
            size_v = tk.StringVar(value=str(original.get("tamanho_iccid") or 20))
            rows = (("Operadora:", op_v), ("Prefixo do ICCID:", prefix_v), ("Tamanho do ICCID:", size_v))
            entries = []
            for r, (label, var) in enumerate(rows):
                ttk.Label(dlg, text=label).grid(row=r, column=0, padx=(16, 8), pady=6, sticky="e")
                ent = ttk.Entry(dlg, textvariable=var, width=28)
                ent.grid(row=r, column=1, padx=(0, 16), pady=6)
                entries.append(ent)
            ttk.Label(dlg, text="O modelo de importação pode ser associado depois pelo botão Modelo de importação.", wraplength=400).grid(row=3, column=0, columnspan=2, padx=16, pady=(4, 8), sticky="w")
            buttons = ttk.Frame(dlg)
            buttons.grid(row=4, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="e")
            ttk.Button(buttons, text="Cancelar", command=dlg.destroy).pack(side="left", padx=(0, 6))

            def save_op():
                op = re.sub(r"\s+", " ", op_v.get().strip()).upper()
                prefix = prefix_v.get().strip()
                try:
                    size = int(size_v.get())
                except ValueError:
                    size = 0
                if not op or not prefix.isdigit() or not (10 <= size <= 30):
                    messagebox.showwarning("Operadora", "Informe o nome, um prefixo somente numérico e um tamanho de ICCID entre 10 e 30.", parent=dlg)
                    return
                for i, rule in enumerate(rules):
                    if i == index:
                        continue
                    if str(rule.get("prefixo") or "") == prefix:
                        messagebox.showwarning("Operadora", "Esse prefixo já está cadastrado neste equipamento.", parent=dlg)
                        return
                    if str(rule.get("operadora") or "").upper() == op:
                        messagebox.showwarning("Operadora", "Essa operadora já está cadastrada neste equipamento.", parent=dlg)
                        return
                old_op = str(original.get("operadora") or "").upper()
                new_rule = {"operadora": op, "prefixo": prefix, "tamanho_iccid": size}
                if index is None:
                    rules.append(new_rule)
                else:
                    rules[index] = new_rule
                templates = cfg.setdefault("exportacoes", {}).setdefault("importacao", {}).setdefault("templates_por_operadora", {})
                if old_op and old_op != op and old_op in templates and op not in templates:
                    templates[op] = templates.pop(old_op)
                self.store.save_equipment_catalog(self.equipments)
                refresh_operators()
                self._refresh_equipment_widgets()
                dlg.destroy()
                status_var.set(f"Operadora {op} salva. O prefixo será usado para identificar cada peça automaticamente.")

            ttk.Button(buttons, text="Salvar", command=save_op).pack(side="left")
            entries[0].bind("<Return>", lambda _e: entries[1].focus_set())
            entries[1].bind("<Return>", lambda _e: entries[2].focus_set())
            entries[2].bind("<Return>", lambda _e: save_op())
            dlg.wait_visibility()
            entries[0].focus_force()

        def choose_operator_model():
            idx = selected_operator_index()
            if idx is None:
                return
            cfg = selected_cfg()
            rules = cfg.get("operadoras_por_prefixo", [])
            if not (0 <= idx < len(rules)):
                return
            op = str(rules[idx].get("operadora") or "").upper()
            path = filedialog.askopenfilename(parent=win, title=f"Selecione o modelo de importação — {op}", filetypes=[("Arquivos do Excel", "*.xls *.xlsx *.xlsm *.xlsb"), ("Todos os arquivos", "*.*")])
            if not path:
                return
            try:
                rel = self._copy_catalog_template(current_key["value"], path, "import", op)
            except Exception as exc:
                messagebox.showerror("Modelo de importação", str(exc), parent=win)
                return
            templates = cfg.setdefault("exportacoes", {}).setdefault("importacao", {}).setdefault("templates_por_operadora", {})
            templates[op] = rel
            self.store.save_equipment_catalog(self.equipments)
            refresh_operators()
            status_var.set(f"Modelo de importação da {op} copiado para DADOS_COMPARTILHADOS.")

        def remove_operator():
            idx = selected_operator_index()
            if idx is None:
                return
            cfg = selected_cfg()
            rules = cfg.get("operadoras_por_prefixo", [])
            if not (0 <= idx < len(rules)):
                return
            op = str(rules[idx].get("operadora") or "").upper()
            if not messagebox.askyesno("Remover operadora", f"Remover {op} deste equipamento?\n\nRegistros antigos não serão apagados, mas novos ICCIDs dessa operadora deixarão de ser aceitos.", parent=win):
                return
            rules.pop(idx)
            templates = cfg.setdefault("exportacoes", {}).setdefault("importacao", {}).setdefault("templates_por_operadora", {})
            templates.pop(op, None)
            self.store.save_equipment_catalog(self.equipments)
            refresh_operators()
            self._refresh_equipment_widgets()
            status_var.set(f"Operadora {op} removida do equipamento.")

        def reload_here():
            try:
                self.equipments = self.store.load_equipment_catalog(self.bundled_equipments)
                refresh_combo()
                load_equipment()
                self._refresh_equipment_widgets()
                status_var.set("Catálogo compartilhado recarregado.")
            except Exception as exc:
                messagebox.showerror("Cadastros", str(exc), parent=win)

        eq_combo.bind("<<ComboboxSelected>>", load_equipment)
        refresh_combo()
        load_equipment()

'''
if settings_marker not in source:
    raise SystemExit("Marcador de Configurações não encontrado")
source = source.replace(settings_marker, catalog_methods + settings_marker, 1)

needle_info = '        info = ttk.LabelFrame(self.tab_settings, text="Configuração atual", padding=14)\n'
manager_box = r'''        catalog = ttk.LabelFrame(self.tab_settings, text="Equipamentos, operadoras e modelos", padding=14)
        catalog.pack(fill="x", pady=(14, 0))
        ttk.Label(
            catalog,
            text=(
                "Cadastros compartilhados entre os PCs: equipamentos, campos, prefixos/tamanhos de ICCID e modelos de exportação. "
                "Um lote pode conter várias operadoras simultaneamente."
            ),
            wraplength=900,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Button(catalog, text="Gerenciar cadastros...", command=self.manage_equipment_catalog).grid(row=1, column=0, sticky="w")
        ttk.Button(catalog, text="Recarregar compartilhado", command=self.reload_shared_catalog).grid(row=1, column=1, sticky="w", padx=(8, 0))
        ttk.Label(catalog, text="Depois de uma alteração, recarregue o catálogo nos outros PCs ou reabra o programa.").grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

'''
if needle_info not in source:
    raise SystemExit("Quadro Configuração atual não encontrado")
source = source.replace(needle_info, manager_box + needle_info, 1)

needle_apply = '        self.store = DataStore(p)\n        self.settings["pasta_compartilhada"] = str(p)\n'
replacement_apply = '        self.store = DataStore(p)\n        self.equipments = self.store.load_equipment_catalog(self.bundled_equipments)\n        self.settings["pasta_compartilhada"] = str(p)\n'
if needle_apply not in source:
    raise SystemExit("Troca de pasta compartilhada não encontrada")
source = source.replace(needle_apply, replacement_apply, 1)

needle_refresh = '        self.profile = self.store.load_user(self.username)\n        self.refresh_lots()\n'
replacement_refresh = '        self.profile = self.store.load_user(self.username)\n        self._refresh_equipment_widgets()\n        self.refresh_lots()\n'
if needle_refresh not in source:
    raise SystemExit("Final da troca de pasta compartilhada não encontrado")
source = source.replace(needle_refresh, replacement_refresh, 1)

required = [
    'APP_VERSION = "0.3.2"',
    'def equipment_catalog_path',
    'def manage_equipment_catalog',
    'shared://',
    'Gerenciar cadastros...',
    'Um lote pode conter várias operadoras',
    'ExcelExporter(self.base_dir, self.equipments[info.equipment_key], self.shared_path)',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.3.2 gerado com sucesso")
