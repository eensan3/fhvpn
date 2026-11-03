# fhvpn

CLI wrapper around [openconnect-sso](https://github.com/vlaci/openconnect-sso) for Cisco AnyConnect–compatible VPN with browser SSO (Firefox / Safari / Qt WebEngine).

Endpoint and email live in `config.local` (gitignored). Copy the example and fill it in.

## Setup

```bash
# deps
brew install openconnect pipx
pipx install "openconnect-sso[full]"
pipx inject openconnect-sso selenium
# Firefox recommended (or Safari + Remote Automation)

cp config.local.example config.local
# edit: VPN_SERVER, VPN_IP, VPN_AUTHGROUP, VPN_USER

./fhvpn setup-creds    # password → macOS Keychain
./fhvpn
```

## Alias

From the repo directory (zsh/bash):

```bash
echo "alias fhvpn='$(pwd)/fhvpn'" >> ~/.zshrc && source ~/.zshrc
```

For bash use `~/.bashrc` instead of `~/.zshrc`.

## Commands

```bash
./fhvpn                  # SSO + tunnel
./fhvpn disconnect
./fhvpn auth             # SSO only
./fhvpn setup-creds
```

Browser: `VPN_BROWSER=firefox` (default) | `safari` | `webengine`.

## Dependencies

- `openconnect` (Homebrew)
- `openconnect-sso[full]` via pipx + `selenium` injected into that venv
- Firefox or Safari
