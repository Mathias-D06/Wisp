"""Job target for spikes/apscheduler_persistence.py (must be importable on its own)."""

RAN: list[str] = []


def job(name: str) -> None:
    RAN.append(name)
