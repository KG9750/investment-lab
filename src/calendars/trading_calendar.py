from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.calendars.providers import MARKET_CALENDAR_NAMES


def get_trading_days(market: str, start: str | date, end: str | date) -> list[date]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    try:
        import pandas_market_calendars as mcal

        calendar = mcal.get_calendar(MARKET_CALENDAR_NAMES.get(market, "NYSE"))
        schedule = calendar.schedule(start_date=start_ts, end_date=end_ts)
        return [pd.Timestamp(idx).date() for idx in schedule.index]
    except Exception:
        days = pd.bdate_range(start_ts, end_ts)
        return [item.date() for item in days]


def next_trading_day(market: str, date_: date) -> date:
    days = get_trading_days(market, date_ + timedelta(days=1), date_ + timedelta(days=14))
    if not days:
        raise ValueError(f"No next trading day found for {market} after {date_}")
    return days[0]


def previous_trading_day(market: str, date_: date) -> date:
    days = get_trading_days(market, date_ - timedelta(days=14), date_ - timedelta(days=1))
    if not days:
        raise ValueError(f"No previous trading day found for {market} before {date_}")
    return days[-1]


def month_end_trading_days(market: str, start: str | date, end: str | date) -> list[date]:
    days = get_trading_days(market, start, end)
    if not days:
        return []
    df = pd.DataFrame({"date": pd.to_datetime(days)})
    grouped = df.groupby(df["date"].dt.to_period("M"))["date"].max()
    return [pd.Timestamp(item).date() for item in grouped]
