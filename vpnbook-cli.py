#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
import json
import logging
import os
import random
import re
import stat
import subprocess
import sys
from bs4 import BeautifulSoup
import httpx

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"

VERSION = "1.0.0"
DEST_DIR = "/etc/openvpn/client"
CONFIG_PATH = os.path.join(DEST_DIR, "vpnbook.conf")
CREDS_PATH = os.path.join(DEST_DIR, "vpnbook_credentials.txt")
URL = "https://www.vpnbook.com/freevpn/openvpn"
URL_API = "https://www.vpnbook.com/api/openvpn"
PROTOCOL = "udp25000"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0"


class ColorFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG: "[ DEBUG ] %(message)s",
        logging.INFO: f"{GREEN}[ INFO ]{RESET} %(message)s",
        logging.WARNING: f"{YELLOW}[ WARNING ]{RESET} %(message)s",
        logging.ERROR: f"{RED}[ ERROR ]{RESET} %(message)s",
        logging.CRITICAL: f"{RED}[ CRITICAL ]{RESET} %(message)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, "%(message)s")
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


@dataclass
class Server:
    hostname: str
    ip_address: str
    country_code: str
    country_name: str
    name: str


@dataclass
class Credentials:
    username: str
    password: str


def fetch_html(url: str) -> str:
    """Makes GET query to URL to get the HTML content."""
    headers = {"User-Agent": USER_AGENT}
    logging.debug("Using headers: %s", headers)
    try:
        with httpx.Client(follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as e:
        logging.critical("Network error: %s", e)
        sys.exit(1)


def parse_credentials(soup: BeautifulSoup) -> Credentials:
    """Parse credentials for OpenVPN."""
    username, password = "", ""

    u_label = soup.find("label", string=lambda t: t and "Username" in t)
    p_label = soup.find("label", string=lambda t: t and "Password" in t)

    if u_label and (u_code := u_label.find_next("code")):
        username = u_code.text.strip()
    if p_label and (p_code := p_label.find_next("code")):
        password = p_code.text.strip()

    logging.debug("Received credentials: username=%s, password=%s", username, password)
    return Credentials(username, password)


def parse_servers(html: str) -> list[Server]:
    """Parse server list from HTML content."""
    servers = []
    match = re.search(r'\\?"servers\\?":\s*(\[.*?\}\s*\])', html)
    if not match:
        return servers

    json_string = match.group(1).replace('\\"', '"')
    try:
        data = json.loads(json_string)
        for s in data:
            servers.append(
                Server(
                    hostname=s.get("hostname", ""),
                    ip_address=s.get("ipAddress", ""),
                    country_code=s.get("countryCode", ""),
                    country_name=s.get("countryName", ""),
                    name=s.get("name", ""),
                )
            )
    except json.JSONDecodeError as e:
        logging.error("Error decoding JSON: %s", e)

    logging.debug(
        "Received servers:\n%s", "".join(f"{s.name}: {s.ip_address}\n" for s in servers)
    )
    return servers


def choose_server(servers: list[Server], use_random: bool) -> Server:
    """Main menu for choosing server."""
    if not servers:
        logging.critical("No servers available to choose from.")
        sys.exit(1)

    if use_random:
        return random.choice(servers)

    print("Choose server to connect:\n")
    for ind, server in enumerate(servers):
        print(f"{GREEN}[{ind + 1}]{RESET} {server.name}")

    while True:
        try:
            choice = int(input("\nYour choice: "))
            if 1 <= choice <= len(servers):
                return servers[choice - 1]
            logging.error("Invalid choice. Out of range.")
        except ValueError:
            logging.error("Invalid choice. Please enter a number.")


def download_config(server: Server, credentials: Credentials) -> None:
    """Downloading config, save creds and vpn config to special directory."""
    download_url = f"{URL_API}?hostname={server.hostname}&protocol={PROTOCOL}&ip={server.ip_address}"
    logging.debug("Downloading config from %s", download_url)

    with httpx.Client() as client:
        config_data = client.get(download_url).text

    logging.debug("Saving creds to %s", CREDS_PATH)
    with open(CREDS_PATH, "w") as f:
        f.write(f"{credentials.username}\n{credentials.password}\n")
    os.chmod(CREDS_PATH, stat.S_IRUSR | stat.S_IWUSR)

    auth_str = f"auth-user-pass {CREDS_PATH}"
    if "auth-user-pass" not in config_data:
        config_data += f"\n{auth_str}\n"
    else:
        lines = config_data.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("auth-user-pass"):
                lines[i] = auth_str
                break
        config_data = "\n".join(lines)

    with open(CONFIG_PATH, "w") as f:
        f.write(config_data)


def manage_vpn(action: str = "start") -> None:
    """Start or stop OpenVPN via systemctl."""
    unit_name = os.path.basename(CONFIG_PATH).removesuffix(".conf")
    command = ["systemctl", action, f"openvpn-client@{unit_name}"]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logging.info("Success %s action for OpenVPN", action)
        if action == "status" and result.stdout:
            logging.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logging.error("Failed to %s OpenVPN. Return code: %s", action, e.returncode)
        if e.stderr:
            logging.error("Details:\n%s", e.stderr)


def setup_logging(verbose: bool) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    httpx_level = logging.INFO if verbose else logging.WARNING

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.addHandler(handler)

    logging.getLogger("httpx").setLevel(httpx_level)


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Script for use free VPNBook OpenVPN services"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable detail output"
    )
    parser.add_argument("-r", "--random", action="store_true", help="use random server")
    parser.add_argument("-s", "--stop", action="store_true", help="stop running VPN")
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    if os.getuid() != 0:
        logging.error("This script must be run as root (sudo).")
        sys.exit(1)

    os.makedirs(DEST_DIR, exist_ok=True)

    if args.stop:
        manage_vpn("stop")
        sys.exit(0)

    if not args.random:
        print(f"{GREEN}Welcome to VPNBook OpenVPN Parser")
        print(f"Version: {VERSION}{RESET}\n")

    html_raw = fetch_html(URL)
    soup = BeautifulSoup(html_raw, "html.parser")

    creds = parse_credentials(soup)
    servers = parse_servers(html_raw)

    server = choose_server(servers, args.random)
    download_config(server, creds)

    manage_vpn("start")


if __name__ == "__main__":
    main()
