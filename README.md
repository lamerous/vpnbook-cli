# vpnbook-cli 🌐

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AUR version](https://img.shields.io/aur/version/vpnbook-cli?color=blue)](https://aur.archlinux.org/packages/vpnbook-cli)

Automated CLI utility to fetch OpenVPN configurations/credentials from VPNBook and connect via systemd on Arch Linux.

## Features
* Automated parsing and credential extraction.
* Native systemd integration (`openvpn-client@`).
* Interactive or randomized (`--random`) server selection.

## Dependencies
* `python (>= 3.10)`
* `python-httpx`
* `python-beautifulsoup4`
* `openvpn`

## Installation

### AUR (Arch Linux)
```bash
yay -S vpnbook-cli
```

### Manual
```bash
git clone https://github.com/lamerous/vpnbook-cli.git
cd vpnbook-cli
pip install -r requirements.txt
sudo install -Dm755 vpnbook-cli.py /usr/bin/vpnbook-cli
sudo install -dm750 /etc/openvpn/client
```

## Usage
Note: Root privileges (`sudo`) are required to manage systemd services and write to `/etc/openvpn/client`.

* Interactive connection:
  ```bash
  sudo vpnbook-cli
  ```

* Connect to a random server:
  ```bash
  sudo vpnbook-cli --random
  ```

* Stop active VPN session:
  ```bash
  sudo vpnbook-cli --stop
  ```

* Debug mode:
  ```bash
  sudo vpnbook-cli --verbose
  ```

## License
[MIT License](LICENSE)
