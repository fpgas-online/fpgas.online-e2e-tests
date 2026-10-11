"""Which boards a run may disrupt.

A disruptive action (the bitstream upload, the power cycle) is only ever taken
on a board the person running the suite named with --boards, and never on a
protected one: a device that must be left exactly as it is. A protected device
is identified by what it is, the Pi's serial number, never by its port or its
hostname, because those move when a board is re-patched or renamed. The serial
-> hostname mapping is read at run time from the site's public registry
(https://<site>/fleet/registry.json, the site's contract for programs; the
/fleet/ page is for people and changes its layout), so a protected device that
now answers to another hostname is still refused.

Fail loud: if the registry cannot be read, or a board named is not in it, the
identity of the board is unknown and nothing disruptive is done to it.
"""

from __future__ import annotations

import dataclasses
import json
import tomllib
import urllib.request
from collections.abc import Callable
from pathlib import Path

from e2e.board import Board
from e2e.site import Site

PROTECTED_FILE = Path(__file__).with_name("protected_boards.toml")


class RegistryError(RuntimeError):
    """The site's registry could not be read as a list of machines."""


@dataclasses.dataclass(frozen=True)
class ProtectedBoard:
    serial: str
    label: str
    reason: str


def load_protected(path: Path = PROTECTED_FILE) -> dict[str, ProtectedBoard]:
    """The protected devices by serial. A malformed entry is an error, never a shorter list."""
    entries = tomllib.loads(path.read_text()).get("protected", [])
    protected: dict[str, ProtectedBoard] = {}
    for entry in entries:
        missing = [key for key in ("serial", "label", "reason") if not str(entry.get(key, "")).strip()]
        if missing:
            raise ValueError(f"{path}: a protected entry lacks {', '.join(missing)}: {entry}")
        protected[entry["serial"].strip().lower()] = ProtectedBoard(
            entry["serial"].strip().lower(), entry["label"].strip(), entry["reason"].strip()
        )
    return protected


def require_named_boards(disruptive: bool, boards_wanted: set[str]) -> None:
    """A disruptive run never chooses its board: it must be told which, with --boards."""
    if disruptive and not boards_wanted:
        raise ValueError(
            "--disruptive needs --boards <hostname[,hostname...]>: the upload and the power cycle are never "
            "run on a board chosen at random or on every board, only on the ones you name"
        )


def _machines(text: str) -> list[dict]:
    """The `machines` list of the site's /fleet/registry.json; RegistryError when the text is not that document."""
    try:
        machines = json.loads(text)["machines"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RegistryError(f"the registry is not the site's registry document: {exc!r}") from exc
    if not isinstance(machines, list) or not all(isinstance(m, dict) for m in machines):
        raise RegistryError("the registry's machines are not a list of objects")
    return machines


def parse_registry(text: str) -> dict[str, str]:
    """hostname -> serial, from the site's /fleet/registry.json.

    A machine with no hostname cannot be named with --boards, so it is not in
    the map. Raises RegistryError for a document that is not the registry, one
    with no named machines, a machine with no serial, or one hostname given two
    serials: any of them means the identities cannot be trusted.
    """
    registry: dict[str, str] = {}
    for machine in _machines(text):
        hostname, serial = machine.get("hostname"), machine.get("serial")
        if not isinstance(serial, str) or not serial.strip():
            raise RegistryError(f"a registry machine has no serial: {machine!r}")
        if not isinstance(hostname, str) or not hostname.strip():
            continue
        hostname, serial = hostname.strip(), serial.strip().lower()
        if registry.get(hostname, serial) != serial:
            raise RegistryError(f"the registry gives {hostname} two serials, {registry[hostname]} and {serial}")
        registry[hostname] = serial
    if not registry:
        raise RegistryError("the registry lists no machines")
    return registry


def http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - a fixed https URL of the site under test
        return response.read().decode("utf-8")


def read_registry(site: Site, fetch: Callable[[str], str] = http_get) -> dict[str, str]:
    """The site's current hostname -> serial map. Raises RegistryError, naming why, if it cannot be had."""
    url = f"{site.base_url}/fleet/registry.json"
    try:
        text = fetch(url)
    except Exception as exc:  # noqa: BLE001 - whatever stopped the read is the reason to report
        raise RegistryError(f"the registry at {url} could not be read: {exc}") from exc
    return parse_registry(text)


def disruption_refusal(board: Board, registry: dict[str, str], protected: dict[str, ProtectedBoard]) -> str:
    """Why `board` must not be disrupted, or "" if it may be."""
    serial = registry.get(board.hostname)
    if serial is None:
        return (
            f"{board.hostname} is not in the site's registry, so its identity is unknown "
            "and nothing disruptive is done to it"
        )
    entry = protected.get(serial)
    if entry is not None:
        return (
            f"{board.hostname} is the protected device {entry.label}: {entry.reason}; "
            "nothing disruptive is done to it"
        )
    return ""


def parse_boards_option(raw: str) -> set[str]:
    """The hostnames in --boards (comma separated, spaces around the commas allowed).

    "" is the option not given: no restriction. Anything else that names no
    board (" ", ",") is an error, never a quiet "no restriction".
    """
    if raw == "":
        return set()
    names = {name.strip() for name in raw.split(",") if name.strip()}
    if not names:
        raise ValueError(f"--boards {raw!r} names no board; give hostnames separated by commas, or leave it out")
    return names


class DisruptionGuard:
    """Answers `refusal(board)`, reading the registry afresh on EVERY call.

    A device can change hostname between one disruptive action and the next (a
    disruptive audit takes minutes per board), so nothing is remembered: each
    answer is one GET made just now. A registry that cannot be read refuses the
    board, with the reason, rather than raising: the caller reports it against
    the board it was about.
    """

    def __init__(self, site: Site, fetch: Callable[[str], str] = http_get, protected: dict | None = None):
        self.site = site
        self.fetch = fetch
        self.protected = load_protected() if protected is None else protected

    def refusal(self, board: Board) -> str:
        try:
            registry = read_registry(self.site, self.fetch)
        except RegistryError as exc:
            return f"{exc}, so the identity of {board.hostname} is unknown and nothing disruptive is done to it"
        return disruption_refusal(board, registry, self.protected)
