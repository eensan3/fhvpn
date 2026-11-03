"""Authenticate Cisco AnyConnect SSO (sso-v2) in a real system browser.

Safari / Firefox support macOS passkeys / Touch ID; Qt WebEngine does not.
Returns the SSO token cookie value (e.g. acSamlv2Token).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from urllib.parse import urlparse

import structlog

log = structlog.get_logger("fhvpn.browser")

FIREFOX_APP = "/Applications/Firefox.app"
FIREFOX_BIN = f"{FIREFOX_APP}/Contents/MacOS/firefox"


def _cookie_map(driver) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in driver.get_cookies():
        name = c.get("name")
        value = c.get("value")
        if name and value:
            out[name] = value
    return out


def _same_page(current: str, final: str) -> bool:
    if not current or not final:
        return False
    if current.rstrip("/") == final.rstrip("/"):
        return True
    return current.startswith(final.rstrip("/") + "?") or current.startswith(
        final.rstrip("/") + "#"
    )


def _config_username() -> str | None:
    cfg = os.path.expanduser("~/.config/openconnect-sso/config.toml")
    try:
        text = open(cfg, encoding="utf-8").read()
    except OSError:
        return None
    in_creds = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_creds = s == "[credentials]"
            continue
        if in_creds and s.startswith("username"):
            _, _, raw = s.partition("=")
            return raw.strip().strip('"').strip("'") or None
    return None


def _resolve_username(credentials: Any) -> str | None:
    user = getattr(credentials, "username", None) if credentials else None
    if user:
        return user
    env = os.environ.get("VPN_USER") or os.environ.get("OPENCONNECT_USER")
    if env:
        return env.strip()
    return _config_username()


def _try_fill_username(driver, username: str | None) -> bool:
    """Fill Microsoft email field. Returns True once value is set."""
    if not username:
        return False
    script = """
    const user = arguments[0];
    const clickNext = arguments[1];
    const selectors = [
      'input[type=email]',
      'input[name=loginfmt]',
      'input[name=username]',
      'input#i0116',
      'input[autocomplete="username"]',
      'input[autocomplete="email"]',
    ];
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      if (!visible || el.disabled || el.readOnly) continue;
      if ((el.value || '') === user) {
        return {selector: sel, already: true};
      }
      el.focus();
      setter.call(el, user);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
      if (clickNext) {
        const next = document.querySelector(
          '#idSIButton9, input[type=submit], button[type=submit]'
        );
        if (next && !next.disabled) next.click();
      }
      return {selector: sel, already: false, value: el.value};
    }
    return null;
    """
    try:
        hit = driver.execute_script(script, username, True)
        if hit:
            log.info(
                "Prefill username",
                selector=hit.get("selector"),
                username=username,
                already=hit.get("already"),
            )
            return True
    except Exception as exc:
        log.debug("Username prefill skipped", error=str(exc))
    return False


def _start_safari():
    from selenium import webdriver
    from selenium.common.exceptions import SessionNotCreatedException
    from selenium.webdriver.safari.options import Options

    opts = Options()
    try:
        return webdriver.Safari(options=opts)
    except SessionNotCreatedException as exc:
        raise RuntimeError(
            "Safari WebDriver недоступен.\n"
            "Один раз включи:\n"
            "  1) Safari → Settings → Advanced → Show features for web developers\n"
            "  2) Safari → Develop → Allow Remote Automation\n"
            "  3) в терминале: sudo safaridriver --enable\n"
            f"Детали: {exc.msg if hasattr(exc, 'msg') else exc}"
        ) from exc


def _start_firefox():
    from selenium import webdriver
    from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
    from selenium.webdriver.firefox.options import Options

    if not os.path.isdir(FIREFOX_APP):
        raise RuntimeError(
            "Firefox не найден в /Applications/Firefox.app.\n"
            "Установи Firefox или используй VPN_BROWSER=safari."
        )

    opts = Options()
    opts.binary_location = FIREFOX_BIN
    # Dedicated profile — always a separate Firefox window for SSO.
    profile_dir = os.path.expanduser("~/.config/fhvpn/firefox-profile")
    os.makedirs(profile_dir, exist_ok=True)
    opts.add_argument("-profile")
    opts.add_argument(profile_dir)
    opts.add_argument("--new-instance")

    try:
        return webdriver.Firefox(options=opts)
    except SessionNotCreatedException as exc:
        raise RuntimeError(
            "Не удалось запустить Firefox через WebDriver.\n"
            f"Детали: {exc.msg if hasattr(exc, 'msg') else exc}"
        ) from exc
    except WebDriverException as exc:
        raise RuntimeError(f"Firefox WebDriver error: {exc}") from exc


def _start_browser(kind: str):
    kind = (kind or "firefox").strip().lower()
    if kind in {"firefox", "ff"}:
        return "firefox", _start_firefox()
    if kind in {"safari", "sf"}:
        return "safari", _start_safari()
    raise RuntimeError(f"Unknown system browser: {kind}")


async def authenticate_in_system_browser(
    proxy: str | None,
    auth_info: Any,
    credentials: Any,
    display_mode: Any = None,
    timeout_sec: int = 15 * 60,
    browser: str | None = None,
) -> str:
    if proxy:
        log.warning("Proxy is set but system-browser path ignores it", proxy=proxy)

    kind = browser or os.environ.get("VPN_BROWSER", "firefox")
    username = _resolve_username(credentials)
    token_name = auth_info.token_cookie_name
    login_url = auth_info.login_url
    final_url = auth_info.login_final_url

    name, driver = await asyncio.to_thread(_start_browser, kind)
    log.info(
        "Opening system browser for SSO",
        browser=name,
        login_url=login_url,
        final_url=final_url,
        token_cookie=token_name,
        username=username,
    )
    if not username:
        log.warning(
            "No username in config/credentials — email will not be autofilled. "
            "Run: fhvpn setup-creds"
        )

    try:
        await asyncio.to_thread(driver.get, login_url)

        deadline = time.monotonic() + timeout_sec
        last_url = ""
        email_filled = False
        while time.monotonic() < deadline:
            current_url = await asyncio.to_thread(lambda: driver.current_url)
            if current_url != last_url:
                log.debug("Browser URL", browser=name, url=current_url)
                last_url = current_url
                email_filled = False

            if username and not email_filled:
                host = urlparse(current_url).hostname or ""
                if (
                    "microsoftonline.com" in host
                    or "microsoft.com" in host
                    or "msauth" in current_url
                    or "login" in current_url.lower()
                ):
                    email_filled = await asyncio.to_thread(
                        _try_fill_username, driver, username
                    )

            cookies = await asyncio.to_thread(_cookie_map, driver)
            token = cookies.get(token_name)
            if token:
                log.info("SSO token cookie captured", browser=name, name=token_name)
                return token

            if _same_page(current_url, final_url):
                await asyncio.sleep(0.5)
                cookies = await asyncio.to_thread(_cookie_map, driver)
                token = cookies.get(token_name)
                if token:
                    log.info(
                        "SSO token cookie captured on final URL",
                        browser=name,
                        name=token_name,
                    )
                    return token

            await asyncio.sleep(0.35)

        raise TimeoutError(
            f"{name} SSO timed out after {timeout_sec}s "
            f"(waiting for cookie {token_name} / {final_url})"
        )
    finally:
        try:
            await asyncio.to_thread(driver.quit)
        except Exception:
            pass


authenticate_in_safari = authenticate_in_system_browser
