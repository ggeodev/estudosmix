import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = Path(os.environ.get("ESTUDOS_ENV", BASE_DIR / ".env"))


def load_env(path=None):
    """Lê KEY=VALUE de .env para os.environ (sem sobrescrever variáveis já definidas)."""
    path = Path(path or ENV_PATH)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def save_env(updates, path=None):
    """Atualiza chaves no .env preservando o resto; também atualiza o processo atual."""
    path = Path(path or ENV_PATH)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in updates and "=" in line and not line.strip().startswith("#"):
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    for k, v in updates.items():
        if k not in done:
            lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    os.environ.update({k: str(v) for k, v in updates.items()})


load_env()


class Config:
    DATABASE_PATH = os.environ.get("ESTUDOS_DB", str(BASE_DIR / "data" / "estudos.db"))
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    HOST = os.environ.get("ESTUDOS_HOST", "127.0.0.1")  # apenas local por padrão
    PORT = int(os.environ.get("ESTUDOS_PORT", "5000"))
    PDF_WORKER = True  # processa PDFs em segundo plano (desligado nos testes)
