from dataclasses import dataclass
from bs4 import BeautifulSoup
import httpx
import re
import json
from colorama import Fore, init
import os
import stat
import sys
import subprocess


VERSION = "0.0.1"
DEST_DIR = "/etc/openvpn/client"
CONFIG_PATH = os.path.join(DEST_DIR, "vpnbook.conf")
CREDS_PATH = os.path.join(DEST_DIR, "vpnbook_credentials.txt")
URL = "https://www.vpnbook.com/freevpn/openvpn"
URL_API = "https://www.vpnbook.com/api/openvpn"
PROTOCOL = "udp25000" # todo: make a choose of them
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0"

os.makedirs(DEST_DIR, exist_ok=True)


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
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


def parse_credentials(soup: BeautifulSoup) -> Credentials:
    username, password = "", ""
    
    u_label = soup.find("label", string=lambda t: t and "Username" in t)
    p_label = soup.find("label", string=lambda t: t and "Password" in t)

    if u_label and (u_code := u_label.find_next("code")):
        username = u_code.text.strip()
    if p_label and (p_code := p_label.find_next("code")):
        password = p_code.text.strip()

    return Credentials(username, password)


def parse_servers(html: str) -> list[Server]:
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
        print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} Error decoding JSON: {e}")
        
    return servers


def choose_server(servers: list[Server]):
    print("Choose server to connect:\n")
    for ind, server in enumerate(servers):
        print(f"{Fore.GREEN}[{ind + 1}]{Fore.WHITE} {server.name}")
    
    while True:
        try:
            choice = int(input("Your choice: "))
            if 1 <= choice <= len(servers):
                return servers[choice - 1]
            else:
                print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} Invalid choice.")
        except ValueError:
            print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} Invalid choice.")


def download_config(server: Server, credentials: Credentials):
    download_url = f"{URL_API}?hostname={server.hostname}&protocol={PROTOCOL}&ip={server.ip_address}"
    print(f"[ INFO ] Downloading config from {download_url}")
    
    with httpx.Client() as client:
        config_data = client.get(download_url).text

    print(f"[ INFO ] Saving creds to {CREDS_PATH}")
    with open(CREDS_PATH, "w") as f:
        f.write(f"{credentials.username}\n{credentials.password}\n")
    os.chmod(CREDS_PATH, stat.S_IRUSR | stat.S_IWUSR)

    if "auth-user-pass" not in config_data:
        config_data += f"\nauth-user-pass {CREDS_PATH}\n"
    else:
        lines = config_data.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("auth-user-pass"):
                lines[i] = f"auth-user-pass {CREDS_PATH}"
                break
        config_data = "\n".join(lines)

    with open(CONFIG_PATH, "w") as f:
        f.write(config_data)


def manage_vpn(action="start"):
    command = ["sudo", "systemctl", action, f"openvpn-client@{CONFIG_PATH.split('/')[-1][:-5]}"]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(" [ INFO ] Success {action} for OpenVPN")
        if action == "status":
            print(result.stdout)

    except subprocess.CalledProcessError as e:
        print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} Return code: {e.returncode}", file=sys.stderr)
        print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} Details:\n{e.stderr}", file=sys.stderr)


def main():
    if os.getuid() != 0:
        print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} This script must be run as root.")
        sys.exit(1)

    print(f"{Fore.GREEN}Welcome to VPNBook OpenVPN Parser")
    print(f"Version: {VERSION}")
    print(Fore.WHITE)

    init(autoreset=True)

    try:
        html_raw = fetch_html(URL)
    except httpx.HTTPError as e:
        print(f"{Fore.RED}[ ERROR ]{Fore.WHITE} Network error: {e}")
        return

    soup = BeautifulSoup(html_raw, "html.parser")
    
    creds = parse_credentials(soup)
    servers = parse_servers(html_raw)

    server = choose_server(servers)
    download_config(server, creds)

    manage_vpn("start")


if __name__ == "__main__":
    main()