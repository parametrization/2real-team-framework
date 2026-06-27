#!/usr/bin/env python3
"""PreToolUse hook: Validate VPS_HOST is not a Cloudflare IP.

Blocks `gh variable set VPS_HOST` if the value resolves to a known Cloudflare
IP range. Also warns if a hostname is used instead of a direct IP.

Exit codes:
  0 — allow (not VPS_HOST, or value is a valid direct IP)
  2 — block (value resolves to Cloudflare IP)
"""

import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annunaki_log import log_pretooluse_block

# Cloudflare publishes their IP ranges at these URLs
_CF_IPV4_URL = "https://www.cloudflare.com/ips-v4"
_CF_IPV6_URL = "https://www.cloudflare.com/ips-v6"

# Local cache file (next to this script) — refreshed at most once per day
_CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_CACHE_DIR, ".cloudflare_ip_cache.json")
_CACHE_MAX_AGE_SECONDS = 86400  # 24 hours

# Fallback static ranges — used when fetch fails and no cache exists
_FALLBACK_RANGES = [
    "104.16.0.0/12",
    "172.64.0.0/13",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "131.0.72.0/22",
]


def _fetch_cloudflare_ranges() -> list[str]:
    """Fetch current Cloudflare IP ranges from their published endpoints."""
    ranges: list[str] = []
    for url in (_CF_IPV4_URL, _CF_IPV6_URL):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                text = resp.read().decode("utf-8")
                for line in text.strip().splitlines():
                    line = line.strip()
                    if line:
                        # Validate it parses as a network
                        ipaddress.ip_network(line, strict=False)
                        ranges.append(line)
        except Exception:
            continue
    return ranges


def _read_cache() -> list[str] | None:
    """Read cached ranges if the cache exists and is fresh."""
    try:
        if not os.path.exists(_CACHE_FILE):
            return None
        age = time.time() - os.path.getmtime(_CACHE_FILE)
        if age > _CACHE_MAX_AGE_SECONDS:
            return None
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        return data.get("ranges")
    except Exception:
        return None


def _write_cache(ranges: list[str]) -> None:
    """Write ranges to the local cache file."""
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump({"ranges": ranges}, f)
    except Exception:
        pass  # Non-fatal — cache is best-effort


def _load_cloudflare_ranges() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Load Cloudflare IP ranges: cache → fetch → fallback."""
    # Try cache first
    cached = _read_cache()
    if cached:
        return [ipaddress.ip_network(r, strict=False) for r in cached]

    # Try fetching
    fetched = _fetch_cloudflare_ranges()
    if fetched:
        _write_cache(fetched)
        return [ipaddress.ip_network(r, strict=False) for r in fetched]

    # Fall back to static list
    return [ipaddress.ip_network(r, strict=False) for r in _FALLBACK_RANGES]


CLOUDFLARE_RANGES = _load_cloudflare_ranges()


def is_cloudflare_ip(ip_str: str) -> bool:
    """Check if an IP address falls within known Cloudflare ranges."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in CLOUDFLARE_RANGES)
    except ValueError:
        return False


def resolve_hostname(hostname: str) -> str | None:
    """Resolve a hostname to an IP address."""
    try:
        return socket.gethostbyname(hostname)
    except (socket.gaierror, socket.timeout):
        return None


def is_ip_address(value: str) -> bool:
    """Check if a string is a valid IP address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def check(input_data: dict) -> dict | None:
    """Check VPS_HOST value. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    match = re.search(r"\bgh\s+variable\s+set\s+VPS_HOST\s+[\"']?(\S+)[\"']?", command)
    if not match:
        return None

    value = match.group(1).strip("\"'")

    if is_ip_address(value):
        ip_to_check = value
        is_hostname_val = False
    else:
        is_hostname_val = True
        ip_to_check = resolve_hostname(value)

    warnings = []

    if is_hostname_val:
        warnings.append(
            f"WARNING: VPS_HOST is a hostname ({value}), not a direct IP. "
            "SSH should use the direct VPS IP to avoid proxy issues."
        )

    if ip_to_check and is_cloudflare_ip(ip_to_check):
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: VPS_HOST value '{value}' resolves to {ip_to_check}, "
                "which is a Cloudflare IP. Cloudflare does not proxy SSH (port 22), "
                "so deploys will fail with connection timeout.\n"
                "Use the direct VPS IP address instead of the proxied domain.\n"
                "Check your hosting provider's dashboard for the origin server IP."
            ),
        }
        log_pretooluse_block("validate_vps_host", command, result["reason"])
        return result

    if warnings:
        return {
            "decision": "allow",
            "systemMessage": "\n".join(warnings),
        }

    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)
    print(json.dumps(result))
    if result.get("decision") == "block":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
