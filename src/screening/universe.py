from __future__ import annotations

from src.config import CONFIG_DIR, load_yaml


def get_universe_config(universe_key: str) -> dict:
    universes = load_yaml(CONFIG_DIR / "universes.yaml")
    if universe_key not in universes:
        raise KeyError(f"Unknown universe: {universe_key}")
    return universes[universe_key]


def get_universe_members(universe_key: str) -> list[str]:
    config = get_universe_config(universe_key)
    members = config.get("members")
    if members:
        return list(members)
    return []
