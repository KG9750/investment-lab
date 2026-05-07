from datetime import date

from src.calendars import get_trading_days, month_end_trading_days, next_trading_day


def test_calendar_basic_functions() -> None:
    days = get_trading_days("US", "2024-01-01", "2024-01-10")
    assert days
    assert next_trading_day("US", date(2024, 1, 1)) > date(2024, 1, 1)
    assert month_end_trading_days("US", "2024-01-01", "2024-03-31")
