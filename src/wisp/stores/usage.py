"""Gemini usage by feature (D-052): requests and tokens, from each response's
``usage_metadata``, for the Stats estimate. Watch-mode looks that were skipped because nothing
changed are counted too (they cost nothing).

Prices are the Gemini API paid tier, Standard, US dollars per million tokens, from
ai.google.dev/gemini-api/docs/pricing (page dated 2026-10-13). They change, so the estimate says
"about" and names the date; a model not listed shows tokens only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from wisp.db import Database

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS ai_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        day TEXT NOT NULL,
        feature TEXT NOT NULL,
        model TEXT NOT NULL,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        skipped INTEGER NOT NULL DEFAULT 0)""",
    "CREATE INDEX IF NOT EXISTS ai_usage_day ON ai_usage(day, feature)",
)
PRICES_CHECKED = "2026-10-13"
# model: [(last day the price applies or None, input $/1M, output $/1M), ...]
PRICES: dict[str, list[tuple[date | None, float, float]]] = {
    "gemini-3.8-flash": [(date(2026, 12, 31), 0.75, 3.75), (None, 1.50, 7.50)],
    "gemini-3.8-flash-tts": [(date(2026, 12, 31), 0.50, 9.00), (None, 1.00, 18.00)],
}


def cost(model: str, input_tokens: int, output_tokens: int, on: date) -> float | None:
    """Estimated US dollars, or None when the model's price isn't known."""
    for last_day, price_in, price_out in PRICES.get(model, []):
        if last_day is None or on <= last_day:
            return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return None


@dataclass
class FeatureUsage:
    feature: str
    requests: int = 0
    skipped: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = 0.0  # None when some model's price is unknown


class UsageStore:
    def __init__(self, db: Database, now: Callable[[], datetime] = lambda: datetime.now()):
        self.db = db
        self.now = now
        self._listeners: list[Callable[[], None]] = []
        with db.transaction() as conn:
            for statement in SCHEMA:
                conn.execute(statement)

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def record(self, feature: str, model: str, input_tokens: int = 0, output_tokens: int = 0,
               skipped: bool = False) -> None:
        now = self.now()
        self.db.execute(
            "INSERT INTO ai_usage(ts, day, feature, model, input_tokens, output_tokens, skipped) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now.isoformat(timespec="seconds"), now.date().isoformat(), feature, model,
             int(input_tokens), int(output_tokens), int(skipped)))
        for listener in list(self._listeners):
            listener()

    def summary(self, first: date, last: date) -> dict[str, FeatureUsage]:
        rows = self.db.query(
            "SELECT day, feature, model, COUNT(*) AS n, SUM(skipped) AS skipped, "
            "SUM(input_tokens) AS i, SUM(output_tokens) AS o FROM ai_usage "
            "WHERE day >= ? AND day <= ? GROUP BY day, feature, model",
            (first.isoformat(), last.isoformat()))
        result: dict[str, FeatureUsage] = {}
        for row in rows:
            usage = result.setdefault(row["feature"], FeatureUsage(row["feature"]))
            skipped = int(row["skipped"] or 0)
            usage.skipped += skipped
            usage.requests += int(row["n"]) - skipped
            usage.input_tokens += int(row["i"] or 0)
            usage.output_tokens += int(row["o"] or 0)
            spent = cost(row["model"], int(row["i"] or 0), int(row["o"] or 0),
                         date.fromisoformat(row["day"]))
            if spent is None or usage.cost is None:
                usage.cost = None if int(row["i"] or 0) + int(row["o"] or 0) else usage.cost
            else:
                usage.cost += spent
        return result

    def today(self) -> dict[str, FeatureUsage]:
        day = self.now().date()
        return self.summary(day, day)
