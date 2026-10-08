"""Exact CMDR display projections prepared off Qt's thread."""
from .dashboard_views import (
    build_commander_cards, build_finance_history, build_finance_summary,
    filter_finance_history,
)


FINANCE_PERIODS = ("session", "1h", "6h", "24h", "7d", "30d", "all")


def prepare_commander_projection(overview, events, credit_snapshots):
    history = build_finance_history(
        events, current_credits=overview.get("credits", {}),
        credit_snapshots=credit_snapshots,
    )
    histories = {period: filter_finance_history(history, period, events)
                 for period in FINANCE_PERIODS}
    return {"cards": build_commander_cards(overview, events),
            "histories": histories,
            "summaries": {period: build_finance_summary(rows)
                          for period, rows in histories.items()}}
