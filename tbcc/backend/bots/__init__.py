# TBCC bots (run with PYTHONPATH=backend or from backend/)
from pathlib import Path
from dotenv import load_dotenv

# Load .env - try tbcc/.env and backend/.env (override=True so .env wins over shell)
_candidates = [
    Path(__file__).resolve().parent.parent.parent / ".env",  # tbcc/.env
    Path(__file__).resolve().parent.parent / ".env",  # backend/.env
    Path.cwd().parent / ".env",  # tbcc/.env when cwd is backend/
    Path.cwd() / ".env",  # backend/.env when cwd is backend/
]
for _p in _candidates:
    if _p.exists():
        load_dotenv(_p, override=True)
        break
