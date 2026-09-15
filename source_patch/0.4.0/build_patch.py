from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.3.5" / "build_patch.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.3.5 não encontrado")

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


source = source.replace('APP_VERSION = "0.3.5"', 'APP_VERSION = "0.4.0"', 1)
if 'APP_VERSION = "0.4.0"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION para 0.4.0")

# zipfile é usado apenas para backup/recuperação local.
if "import zipfile\n" not in source:
    replace_once("import urllib.request\n", "import urllib.request\nimport zipfile\n", "import zipfile")

# -----------------------------------------------------------------------------
# Etapa 10 — consolidação: backup local, recuperação não destrutiva e fechamento
# da fase 0.3.x sem alterar as regras operacionais dos lotes.
# -----------------------------------------------------------------------------
settings_marker = "    # ---------------- Configurações ----------------\n"
backup_methods = r'''    # ---------------- Backup e recuperação ----------------
    def _backup_dir(self) -> Path:
        path = local_config_dir() / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _backup_status_text(self) -> str:
        folder = self._backup_dir()
        items = sorted(folder.glob("Planilhador_Backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not items:
            return "Nenhum backup local criado neste computador."
        latest = items[0]
        try:
            stamp = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            size_mb = latest.stat().st_size / (1024 * 1024)
            return f"Último backup: {stamp}  •  {latest.name}  •  {size_mb:.1f} MB"
        except OSError:
            return f"Último backup: {latest.name}"

    def _refresh_backup_status(self):
        if hasattr(self, "backup_status_var"):
            self.backup_status_var.set(self._backup_status_text())

    @staticmethod
    def _backup_allowed_relative(rel: Path) -> bool:
        if not rel.parts:
            return False
        if rel.name == ".lock" or rel.suffix.lower() == ".tmp":
            return False
        if rel.name.startswith(".diagnostico_"):
            return False
        return rel.parts[0] in {"lotes", "usuarios", "configuracao", "catalogo_modelos"}

    def create_shared_backup(self, show_message: bool = True) -> Path | None:
        if not self.shared_path.exists():
            if show_message:
                messagebox.showerror("Backup", "A pasta compartilhada não está disponível.")
            return None

        destination = self._backup_dir()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = destination / f"Planilhador_Backup_{stamp}.zip"
        temp_path = final_path.with_suffix(".zip.tmp")
        file_count = 0
        total_bytes = 0

        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for path in sorted(self.shared_path.rglob("*")):
                    if not path.is_file():
                        continue
                    try:
                        rel = path.relative_to(self.shared_path)
                    except ValueError:
                        continue
                    if not self._backup_allowed_relative(rel):
                        continue
                    zf.write(path, rel.as_posix())
                    file_count += 1
                    try:
                        total_bytes += path.stat().st_size
                    except OSError:
                        pass

                manifest = {
                    "tipo": "Planilhador de Equipamentos - backup",
                    "versao_programa": APP_VERSION,
                    "criado_em": now_iso(),
                    "arquivos": file_count,
                    "bytes_origem": total_bytes,
                    "origem_pc": self.store.computer_name(),
                }
                zf.writestr("BACKUP_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            os.replace(temp_path, final_path)
        except Exception as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            if show_message:
                messagebox.showerror("Backup", f"Não foi possível criar o backup:\n{exc}")
            return None

        self.settings["ultimo_backup_local"] = str(final_path)
        self.settings["ultimo_backup_em"] = now_iso()
        self.save_local_settings()
        self._refresh_backup_status()
        if show_message:
            messagebox.showinfo(
                "Backup concluído",
                f"Backup criado com sucesso.\n\nArquivos: {file_count}\nLocal:\n{final_path}\n\n"
                "Este backup fica fora da pasta compartilhada/OneDrive deste programa.",
            )
        return final_path

    def open_backup_folder(self):
        folder = self._backup_dir()
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Backups", f"Não foi possível abrir a pasta de backups:\n{exc}")

    def recover_backup_to_new_folder(self):
        backup = filedialog.askopenfilename(
            title="Selecione um backup do Planilhador",
            initialdir=str(self._backup_dir()),
            filetypes=[("Backup do Planilhador", "*.zip"), ("Arquivos ZIP", "*.zip")],
        )
        if not backup:
            return
        backup_path = Path(backup)

        parent = filedialog.askdirectory(
            title="Escolha onde criar a pasta recuperada (não sobrescreve a pasta atual)"
        )
        if not parent:
            return
        target = Path(parent) / ("Planilhador_Recuperado_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        target.mkdir(parents=True, exist_ok=False)

        extracted = 0
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                names = zf.namelist()
                if "BACKUP_MANIFEST.json" not in names:
                    raise ValueError("O arquivo selecionado não possui o manifesto de backup do Planilhador.")
                try:
                    manifest = json.loads(zf.read("BACKUP_MANIFEST.json").decode("utf-8"))
                except Exception as exc:
                    raise ValueError(f"Manifesto de backup inválido: {exc}")
                if "Planilhador" not in str(manifest.get("tipo") or ""):
                    raise ValueError("Este ZIP não foi reconhecido como backup do Planilhador.")

                root_resolved = target.resolve()
                for member in zf.infolist():
                    if member.is_dir() or member.filename == "BACKUP_MANIFEST.json":
                        continue
                    rel = Path(member.filename.replace("\\", "/"))
                    if rel.is_absolute() or ".." in rel.parts or not self._backup_allowed_relative(rel):
                        raise ValueError(f"Caminho inválido encontrado no backup: {member.filename}")
                    dest = (target / rel).resolve()
                    if dest != root_resolved and root_resolved not in dest.parents:
                        raise ValueError(f"Caminho fora da pasta de recuperação: {member.filename}")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
                    extracted += 1
        except Exception as exc:
            try:
                shutil.rmtree(target, ignore_errors=True)
            except OSError:
                pass
            messagebox.showerror("Recuperar backup", f"Não foi possível recuperar o backup:\n{exc}")
            return

        if extracted == 0:
            shutil.rmtree(target, ignore_errors=True)
            messagebox.showerror("Recuperar backup", "O backup não contém dados recuperáveis.")
            return

        switch_now = messagebox.askyesno(
            "Backup recuperado",
            f"A recuperação foi criada sem alterar os dados atuais.\n\nPasta recuperada:\n{target}\n\n"
            "Deseja apontar ESTE computador para a pasta recuperada agora?\n\n"
            "Se usar essa recuperação em produção, os outros PCs também deverão apontar para a mesma pasta.",
        )
        if not switch_now:
            return
        if self.session_records:
            messagebox.showwarning(
                "Trocar pasta compartilhada",
                "Há peças nesta sessão. A pasta recuperada foi criada, mas não será aplicada até a sessão estar vazia.",
            )
            return
        self.shared_var.set(str(target))
        self.apply_shared()

'''
if settings_marker not in source:
    raise SystemExit("Marcador de Configurações não encontrado")
source = source.replace(settings_marker, backup_methods + settings_marker, 1)

# Quadro de backup antes da área de diagnóstico, mantendo Configurações organizada.
needle_robustness = '        robustness = ttk.LabelFrame(self.tab_settings, text="Diagnóstico e robustez", padding=14)\n'
backup_box = r'''        backup_box = ttk.LabelFrame(self.tab_settings, text="Backup e recuperação", padding=14)
        backup_box.pack(fill="x", pady=(14, 0))
        ttk.Label(
            backup_box,
            text=(
                "Cria uma cópia local dos lotes, usuários, catálogo compartilhado e modelos personalizados. "
                "A recuperação sempre é extraída para uma NOVA pasta para não sobrescrever dados sincronizados por engano."
            ),
            wraplength=900,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Button(
            backup_box,
            text="Criar backup agora",
            command=self.create_shared_backup,
            style="Primary.TButton",
        ).grid(row=1, column=0, sticky="w")
        ttk.Button(
            backup_box,
            text="Recuperar backup...",
            command=self.recover_backup_to_new_folder,
        ).grid(row=1, column=1, sticky="w", padx=(8, 0))
        ttk.Button(
            backup_box,
            text="Abrir pasta de backups",
            command=self.open_backup_folder,
        ).grid(row=1, column=2, sticky="w", padx=(8, 0))
        self.backup_status_var = tk.StringVar(value=self._backup_status_text())
        ttk.Label(
            backup_box,
            textvariable=self.backup_status_var,
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(
            backup_box,
            text="Recomendação: feche o Planilhador nos outros PCs antes de trocar para uma pasta recuperada.",
            style="Muted.TLabel",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))

'''
replace_once(needle_robustness, backup_box + needle_robustness, "quadro de backup")

# Consolidação das mensagens da tela de configurações: versão e papel do diagnóstico.
needle_heading = (
    '            text="Ajuste compartilhamento, atualizações e cadastros sem interferir nos lotes já gravados.",\n'
)
if needle_heading in source:
    source = source.replace(
        needle_heading,
        '            text="Compartilhamento, atualizações, cadastros, backup e diagnóstico em um único lugar.",\n',
        1,
    )

# Ao aplicar uma pasta compartilhada, atualiza também o status do backup e deixa
# explícito que a troca foi local neste computador.
needle_apply_message = '        messagebox.showinfo("Pasta compartilhada", "Pasta aplicada. Use exatamente esta mesma pasta nos outros PCs.")\n'
replacement_apply_message = r'''        self._refresh_backup_status()
        messagebox.showinfo(
            "Pasta compartilhada",
            "Pasta aplicada neste computador. Se ela for usada em produção, configure os outros PCs para apontar para a mesma pasta.",
        )
'''
replace_once(needle_apply_message, replacement_apply_message, "mensagem consolidada de pasta compartilhada")

required = [
    'APP_VERSION = "0.4.0"',
    'import zipfile',
    'def create_shared_backup',
    'def recover_backup_to_new_folder',
    'BACKUP_MANIFEST.json',
    'Backup e recuperação',
    'Criar backup agora',
    'Recuperar backup...',
    'A recuperação sempre é extraída para uma NOVA pasta',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.4.0 gerado com sucesso — Etapa 10 consolidação")
