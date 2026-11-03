"""Back-compat shim — use fhvpn_browser_auth."""
import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parent / "fhvpn_browser_auth.py"
_spec = importlib.util.spec_from_file_location("fhvpn_browser_auth", _path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
authenticate_in_safari = _mod.authenticate_in_system_browser
authenticate_in_system_browser = _mod.authenticate_in_system_browser
