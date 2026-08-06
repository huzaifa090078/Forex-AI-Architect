"""
Trading Session Detection — Section 4 Market Scanner.

Identifies which major forex trading session is currently active based on
UTC time.  No external dependencies; pure datetime arithmetic.

Sessions (all times UTC):
  Asian          00:00 – 09:00
  London         07:00 – 16:00
  New York       12:00 – 21:00
  London/NY Overlap  12:00 – 16:00  (both markets active simultaneously)
  Off Hours      21:00 – 00:00  (no major session open)

Usage:
    from app.modules.market_scanner.session import get_current_session, TradingSession

    session = get_current_session()         # uses datetime.now(UTC)
    session = get_current_session(some_dt)  # explicit datetime (aware or naive UTC)

    print(session)         # e.g. TradingSession.OVERLAP
    print(session.value)   # e.g. "London/NY Overlap"
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class TradingSession(str, Enum):
    """Active major forex trading session."""

    ASIAN     = "Asian"
    LONDON    = "London"
    NEW_YORK  = "New York"
    OVERLAP   = "London/NY Overlap"
    OFF_HOURS = "Off Hours"


def get_current_session(dt: Optional[datetime] = None) -> TradingSession:
    """
    Return the trading session that is active at `dt` (UTC).

    Parameters
    ----------
    dt : datetime | None
        Datetime to evaluate.  If None, uses the current UTC time.
        Naive datetimes are treated as UTC.

    Returns
    -------
    TradingSession
        The dominant session at the given time.  When both London and
        New York are open (12:00–16:00 UTC), OVERLAP is returned.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        # Treat naive datetime as UTC — consistent with the rest of the project
        dt = dt.replace(tzinfo=timezone.utc)

    hour: int = dt.hour  # 0–23 UTC

    in_asian    = 0 <= hour < 9
    in_london   = 7 <= hour < 16
    in_new_york = 12 <= hour < 21

    # Overlap takes priority — both London and New York desks are active
    if in_london and in_new_york:
        return TradingSession.OVERLAP

    if in_london:
        return TradingSession.LONDON

    if in_new_york:
        return TradingSession.NEW_YORK

    if in_asian:
        return TradingSession.ASIAN

    return TradingSession.OFF_HOURS
