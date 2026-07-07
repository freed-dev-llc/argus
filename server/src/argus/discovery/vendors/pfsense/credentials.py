"""Credential loading for pfSense/OPNsense SSH and SNMP access.

Supports multiple credential patterns:
- Direct values in environment variables (existing behavior)
- File paths with JSON key extraction: PFSENSE_USERNAME="~/.secrets/lab-opnsense-creds:username"
- Plain text files: PFSENSE_USERNAME="~/.secrets/lab-opnsense-username"
"""

from __future__ import annotations

import json
import os


def _read_secret_file(path: str) -> str:
    """Read and strip a JSON or plaintext secrets file.

    If the file contains valid JSON and a top-level object, treats it as JSON.
    Otherwise, reads it as plaintext and returns stripped contents.
    """
    expanded = os.path.expanduser(path)
    with open(expanded) as f:
        content = f.read().strip()

    # Try JSON parsing for convenience
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # If it's a dict, return it for later extraction
            return json.dumps(data)
        # If it's not a dict, treat as plaintext
        return content
    except json.JSONDecodeError:
        # Not JSON, return as plaintext
        return content


def load_ssh_creds(host: str, username: str, password: str) -> tuple[str, str, str]:
    """Resolve SSH credentials from env values or file paths.

    Supports three patterns:
    1. Direct values: "admin" → "admin"
    2. File paths with JSON keys: "~/.secrets/creds:username" → read file, extract JSON key
    3. Plain files: "~/.secrets/username-file" → read file contents

    Args:
        host: SSH host (may be env var reference for expansion)
        username: Username (raw value or file path pattern)
        password: Password (raw value or file path pattern)

    Returns:
        Tuple of (resolved_host, resolved_username, resolved_password)

    Raises:
        FileNotFoundError: If a referenced file does not exist
        json.JSONDecodeError: If JSON extraction is requested but file is invalid JSON
        KeyError: If a JSON key is requested but not present in the file
    """

    def resolve_value(value: str) -> str:
        """Resolve a single credential value from env var or file."""
        if not value:
            return value

        # Check if it looks like a file path with JSON key extraction (file:key pattern)
        if ":" in value and not value.startswith(":"):
            parts = value.rsplit(":", 1)
            if len(parts) == 2:
                path_part, key_part = parts
                # Check if path_part looks like a file path
                if "/" in path_part or path_part.startswith("~"):
                    expanded_path = os.path.expanduser(path_part)
                    # This looks like a file:key pattern; file must exist
                    if not os.path.exists(expanded_path):
                        raise FileNotFoundError(f"Credential file not found: {path_part}")
                    try:
                        content = _read_secret_file(path_part)
                        data = json.loads(content)
                        if isinstance(data, dict) and key_part in data:
                            return str(data[key_part])
                        # If JSON key doesn't exist, raise error
                        raise KeyError(f"Key '{key_part}' not found in {path_part}") from None
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid JSON in credential file {path_part}: {exc}") from exc

        # Check if it's a file path without JSON key (plain file)
        if "/" in value or value.startswith("~"):
            expanded_path = os.path.expanduser(value)
            if os.path.exists(expanded_path):
                return _read_secret_file(value)
            # If it looks like a file path but doesn't exist, raise error
            # (avoid treating it as a literal username/password)
            if "/" in value or value.startswith("~"):
                raise FileNotFoundError(f"Credential file not found: {value}")

        # Treat as a direct value
        return value

    return (resolve_value(host), resolve_value(username), resolve_value(password))


def load_snmp_creds(community: str) -> str:
    """Resolve SNMP community string from env value or file path.

    Supports:
    1. Direct values: "public" → "public"
    2. File paths: "~/.secrets/snmp-community" → read file contents

    Args:
        community: Community string (raw value or file path)

    Returns:
        Resolved community string

    Raises:
        FileNotFoundError: If a referenced file does not exist
    """
    if not community:
        return community

    # Check if it's a file path
    if "/" in community or community.startswith("~"):
        expanded_path = os.path.expanduser(community)
        if os.path.exists(expanded_path):
            return _read_secret_file(community)

    # Treat as a direct value
    return community
