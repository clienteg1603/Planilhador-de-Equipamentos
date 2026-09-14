from pathlib import Path
import re
import subprocess
import sys

ROOT = Path.cwd()
BASE_BUILDER = ROOT / "source_patch" / "0.2.8" / "build_patch_fix.py"
if not BASE_BUILDER.exists():
    raise SystemExit("Gerador base da v0.2.8 não encontrado")

subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
source_path = ROOT / "Planilhador.pyw"
source = source_path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str) -> None:
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Falha ao aplicar patch: {label} (ocorrências={count})")


source = source.replace('APP_VERSION = "0.2.8"', 'APP_VERSION = "0.2.9"', 1)
if 'APP_VERSION = "0.2.9"' not in source:
    raise SystemExit("Não foi possível atualizar APP_VERSION")

# -----------------------------------------------------------------------------
# Usuários: descoberta dos já cadastrados, nome canônico e criação sem duplicar.
# -----------------------------------------------------------------------------
marker_user_path = "    def user_path(self, username: str) -> Path:\n"
user_helpers = r'''    @staticmethod
    def normalize_username(username: str) -> str:
        return re.sub(r"\s+", " ", str(username or "").strip())

    @classmethod
    def username_key(cls, username: str) -> str:
        return cls.normalize_username(username).casefold()

    def list_users(self) -> list[str]:
        users_dir = self.root / "usuarios"
        users_dir.mkdir(parents=True, exist_ok=True)
        found = {}
        for path in sorted(users_dir.glob("*.json")):
            data = read_json(path, {}) or {}
            name = self.normalize_username(data.get("nome") or path.stem)
            if len(name) < 2:
                continue
            key = self.username_key(name)
            if key not in found:
                found[key] = name
        return sorted(found.values(), key=lambda x: x.casefold())

    def canonical_username(self, username: str) -> str | None:
        wanted = self.username_key(username)
        if not wanted:
            return None
        for name in self.list_users():
            if self.username_key(name) == wanted:
                return name
        return None

    def create_user(self, username: str) -> tuple[str, bool]:
        clean = self.normalize_username(username)
        if len(clean) < 2:
            raise ValueError("Digite um nome/login com pelo menos 2 caracteres.")
        existing = self.canonical_username(clean)
        if existing:
            return existing, False
        profile = {
            "nome": clean,
            "sequencias": {},
            "criado_em": now_iso(),
        }
        self.save_user(profile)
        return clean, True

'''
if marker_user_path not in source:
    raise SystemExit("Ponto de inserção dos usuários não encontrado")
source = source.replace(marker_user_path, user_helpers + marker_user_path, 1)

# -----------------------------------------------------------------------------
# Login: escolher usuário existente ou criar um novo sem digitação repetida.
# -----------------------------------------------------------------------------
new_login = r'''    def login_dialog(self) -> bool:
        dialog = tk.Toplevel(self)
        dialog.title("Entrar")
        dialog.resizable(False, False)
        dialog.grab_set()
        ok = {"value": False}

        ttk.Label(dialog, text=APP_NAME, font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, padx=28, pady=(24, 6), sticky="w"
        )
        ttk.Label(dialog, text="Selecione quem vai usar este computador agora:").grid(
            row=1, column=0, columnspan=2, padx=28, pady=(12, 5), sticky="w"
        )

        name_var = tk.StringVar()
        combo = ttk.Combobox(dialog, textvariable=name_var, state="readonly", width=34)
        combo.grid(row=2, column=0, columnspan=2, padx=28, pady=(0, 6), sticky="ew")

        hint_var = tk.StringVar()
        ttk.Label(dialog, textvariable=hint_var, wraplength=390).grid(
            row=3, column=0, columnspan=2, padx=28, pady=(0, 14), sticky="w"
        )

        def refresh_users(prefer: str | None = None):
            users = self.store.list_users()
            combo["values"] = users
            wanted = prefer or self.settings.get("ultimo_usuario", "")
            canonical = self.store.canonical_username(wanted) if wanted else None
            if canonical:
                name_var.set(canonical)
            elif users:
                name_var.set(users[0])
            else:
                name_var.set("")
            if users:
                hint_var.set("A sequência de bipagem continua sendo individual para cada usuário.")
            else:
                hint_var.set("Nenhum usuário cadastrado ainda. Clique em Novo usuário para criar o primeiro.")
            enter_btn.config(state="normal" if users else "disabled")

        def create_new_user():
            win = tk.Toplevel(dialog)
            win.title("Novo usuário")
            win.resizable(False, False)
            win.transient(dialog)
            win.grab_set()

            ttk.Label(win, text="Novo usuário", font=("Segoe UI", 13, "bold")).grid(
                row=0, column=0, columnspan=2, padx=22, pady=(20, 8), sticky="w"
            )
            ttk.Label(win, text="Nome/login:").grid(row=1, column=0, padx=(22, 8), pady=6, sticky="e")
            new_var = tk.StringVar()
            entry = ttk.Entry(win, textvariable=new_var, width=32)
            entry.grid(row=1, column=1, padx=(0, 22), pady=6)
            msg_var = tk.StringVar(value="Espaços extras e diferenças entre maiúsculas/minúsculas não criam usuários duplicados.")
            ttk.Label(win, textvariable=msg_var, wraplength=390).grid(
                row=2, column=0, columnspan=2, padx=22, pady=(4, 10), sticky="w"
            )

            def save_new(*_):
                try:
                    canonical, created = self.store.create_user(new_var.get())
                except ValueError as exc:
                    msg_var.set(str(exc))
                    self.bell()
                    entry.focus_set()
                    entry.selection_range(0, "end")
                    return
                refresh_users(canonical)
                win.destroy()
                if created:
                    hint_var.set(f"Usuário {canonical} criado e selecionado.")
                else:
                    hint_var.set(f"Esse usuário já existia. {canonical} foi selecionado.")
                combo.focus_set()

            buttons = ttk.Frame(win)
            buttons.grid(row=3, column=0, columnspan=2, padx=22, pady=(4, 18), sticky="e")
            ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side="left", padx=(0, 8))
            ttk.Button(buttons, text="Criar", command=save_new).pack(side="left")
            entry.bind("<Return>", save_new)
            win.bind("<Escape>", lambda _e: win.destroy())
            win.wait_visibility()
            entry.focus_force()

        def enter(*_):
            selected = name_var.get().strip()
            canonical = self.store.canonical_username(selected)
            if not canonical:
                messagebox.showwarning("Login", "Selecione um usuário cadastrado ou crie um novo.", parent=dialog)
                return
            self.username = canonical
            self.profile = self.store.load_user(canonical)
            self.settings["ultimo_usuario"] = canonical
            self.save_local_settings()
            ok["value"] = True
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=4, column=0, columnspan=2, padx=28, pady=(2, 24), sticky="e")
        ttk.Button(buttons, text="Novo usuário", command=create_new_user).pack(side="left", padx=(0, 8))
        enter_btn = ttk.Button(buttons, text="Entrar", command=enter)
        enter_btn.pack(side="left")

        combo.bind("<Return>", enter)
        combo.bind("<<ComboboxSelected>>", lambda _e: hint_var.set(
            f"Usuário selecionado: {name_var.get()} — a sequência de bipagem dele será carregada."
        ))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        refresh_users()
        dialog.wait_visibility()
        combo.focus_force()
        self.wait_window(dialog)
        return ok["value"]
'''
sub_once(r'    def login_dialog\(self\) -> bool:.*?(?=\n    def save_local_settings\()', new_login, "login_dialog")

# Informação na tela de Configurações.
needle_info = '        ttk.Label(info, text="Bipagem: feedback visual, última peça destacada e ação para desfazer a última peça sem interromper o fluxo.").pack(anchor="w", pady=3)\n'
replacement_info = needle_info + '        ttk.Label(info, text="Usuários: login por seleção, criação controlada e sequência de bipagem individual por funcionário.").pack(anchor="w", pady=3)\n'
if needle_info not in source:
    raise SystemExit("Texto de configuração da v0.2.8 não encontrado")
source = source.replace(needle_info, replacement_info, 1)

required = [
    'APP_VERSION = "0.2.9"',
    'def list_users',
    'def canonical_username',
    'def create_user',
    'Novo usuário',
    'Selecione quem vai usar este computador agora',
    'A sequência de bipagem continua sendo individual',
]
for token in required:
    if token not in source:
        raise SystemExit(f"Patch incompleto: {token}")

source_path.write_text(source, encoding="utf-8")
print("Planilhador.pyw v0.2.9 gerado com sucesso")
