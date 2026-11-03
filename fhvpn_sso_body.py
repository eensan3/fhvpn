"""openconnect-sso wrapper for fhvpn.

Default SSO browser: Firefox.
Also: VPN_BROWSER=safari | webengine
"""

import getpass
import importlib.util
import os
import sys
from pathlib import Path

_orig_getpass = getpass.getpass


def _getpass(prompt="", stream=None):
    if "TOTP secret" in prompt or prompt.startswith("Password"):
        return ""
    return _orig_getpass(prompt, stream)


getpass.getpass = _getpass

from openconnect_sso.config import Credentials

_orig_password_set = Credentials.password.fset


@Credentials.password.setter
def _password_setter(self, value):
    if not value:
        return
    _orig_password_set(self, value)


def _browser_backend() -> str:
    # VPN_BROWSER: firefox (default) | safari | webengine | shown | hidden
    raw = os.environ.get("VPN_BROWSER", "firefox").strip().lower()
    if raw in {"webengine", "qt", "shown", "hidden"}:
        return "webengine"
    if raw in {"safari", "sf"}:
        return "safari"
    return "firefox"


def _install_persistent_webengine():
    """Replace stock in-memory Qt profile with disk-backed one (SSO cookies)."""
    patched = Path(__file__).resolve().parent / "fhvpn_webengine_process.py"
    if not patched.is_file():
        return

    name = "openconnect_sso.browser.webengine_process"
    if name in sys.modules:
        return

    spec = importlib.util.spec_from_file_location(name, patched)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)


def _install_system_browser_auth(kind: str):
    path = Path(__file__).resolve().parent / "fhvpn_browser_auth.py"
    spec = importlib.util.spec_from_file_location("fhvpn_browser_auth", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    import openconnect_sso.saml_authenticator as saml

    async def _auth(proxy, auth_info, credentials, display_mode):
        return await mod.authenticate_in_system_browser(
            proxy, auth_info, credentials, display_mode, browser=kind
        )

    saml.authenticate_in_browser = _auth


backend = _browser_backend()
if backend in {"safari", "firefox"}:
    _install_system_browser_auth(backend)
else:
    _install_persistent_webengine()

from openconnect_sso.cli import main

if __name__ == "__main__":
    sys.argv[0] = sys.argv[0].removesuffix(".exe")
    raise SystemExit(main())
