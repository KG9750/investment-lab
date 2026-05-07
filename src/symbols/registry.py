from __future__ import annotations

from src.storage.duckdb_client import connect
from src.storage.metadata import utc_now_str


def upsert_symbol(
    unified_symbol: str,
    market: str,
    provider: str,
    provider_symbol: str,
    asset_type: str = "equity",
    exchange: str | None = None,
    name: str | None = None,
    currency: str | None = None,
    timezone: str | None = None,
) -> None:
    now = utc_now_str()
    with connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO symbol_master
            VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, COALESCE(
                (SELECT first_seen_at FROM symbol_master WHERE unified_symbol = ?), ?), ?)
            """,
            [
                unified_symbol,
                market,
                asset_type,
                exchange,
                name,
                currency,
                timezone,
                unified_symbol,
                now,
                now,
            ],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO symbol_provider_map
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [unified_symbol, provider, provider_symbol, market, exchange, now],
        )
