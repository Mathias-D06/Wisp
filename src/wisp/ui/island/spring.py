"""Damped springs for the island's shape (D-045).

Each channel (width, height, the split circle …) is a unit-mass spring x'' = −k·x − c·x' around
its target, stepped with the exact closed-form solution, so the motion is the same at any frame
rate and a long frame can't make it unstable. Retargeting keeps the current value and velocity,
so an interrupted transition carries on smoothly from wherever it is. A spring with
``overshoot=False`` stops at its target instead of crossing it (collapses never overshoot).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from wisp.ui.theme import ISLAND, SpringTokens

SETTLE_DISTANCE = 0.25  # px
SETTLE_SPEED = 3.0  # px/s


@dataclass
class Spring:
    value: float
    target: float | None = None
    velocity: float = 0.0
    stiffness: float = ISLAND.expand.stiffness
    damping_ratio: float = ISLAND.expand.damping_ratio
    overshoot: bool = True

    def __post_init__(self) -> None:
        if self.target is None:
            self.target = self.value

    @property
    def settled(self) -> bool:
        return (abs(self.value - self.target) < SETTLE_DISTANCE
                and abs(self.velocity) < SETTLE_SPEED)

    def retarget(self, target: float, tokens: SpringTokens, overshoot: bool = True) -> None:
        """New target and constants; value and velocity carry over (no jump)."""
        self.target = float(target)
        self.stiffness = tokens.stiffness
        self.damping_ratio = tokens.damping_ratio
        self.overshoot = overshoot

    def jump(self, value: float) -> None:
        """Snap to ``value`` at rest (motion off)."""
        self.value = self.target = float(value)
        self.velocity = 0.0

    def step(self, dt: float) -> None:
        if dt <= 0 or self.settled:
            if self.settled:
                self.value, self.velocity = self.target, 0.0
            return
        x0 = self.value - self.target
        x, v = damped(x0, self.velocity, self.stiffness, self.damping_ratio, dt)
        if not self.overshoot and x0 != 0 and math.copysign(1, x) != math.copysign(1, x0):
            x, v = 0.0, 0.0  # reached the target: stop there instead of crossing it
        self.value, self.velocity = self.target + x, v
        if self.settled:
            self.value, self.velocity = self.target, 0.0


def damped(x0: float, v0: float, stiffness: float, ratio: float, t: float) -> tuple[float, float]:
    """Position and velocity (relative to the target) after ``t`` seconds."""
    omega = math.sqrt(stiffness)
    if abs(ratio - 1.0) < 1e-6:  # critically damped
        c = v0 + omega * x0
        decay = math.exp(-omega * t)
        return (x0 + c * t) * decay, (v0 - omega * c * t) * decay
    if ratio < 1.0:  # under-damped
        alpha = ratio * omega
        wd = omega * math.sqrt(1.0 - ratio * ratio)
        b = (v0 + alpha * x0) / wd
        decay = math.exp(-alpha * t)
        cos, sin = math.cos(wd * t), math.sin(wd * t)
        return decay * (x0 * cos + b * sin), decay * (v0 * cos - (alpha * b + x0 * wd) * sin)
    root = math.sqrt(ratio * ratio - 1.0)  # over-damped
    r1, r2 = -omega * (ratio - root), -omega * (ratio + root)
    c2 = (v0 - r1 * x0) / (r2 - r1)
    c1 = x0 - c2
    e1, e2 = math.exp(r1 * t), math.exp(r2 * t)
    return c1 * e1 + c2 * e2, r1 * c1 * e1 + r2 * c2 * e2


class SpringSet:
    """Named springs moved towards targets together; picks the constants per channel."""

    def __init__(self, **values: float):
        self.springs = {name: Spring(float(value)) for name, value in values.items()}

    def __getitem__(self, name: str) -> float:
        return self.springs[name].value

    @property
    def settled(self) -> bool:
        return all(spring.settled for spring in self.springs.values())

    def retarget(self, animate: bool = True, **targets: float) -> None:
        for name, target in targets.items():
            spring = self.springs[name]
            if not animate:
                spring.jump(target)
                continue
            if target == spring.target and not spring.settled:
                continue  # already heading there
            delta = target - spring.value
            if abs(delta) < ISLAND.small_px:
                spring.retarget(target, ISLAND.small, overshoot=delta > 0)
            elif delta > 0:
                spring.retarget(target, ISLAND.expand, overshoot=True)
            else:
                spring.retarget(target, ISLAND.collapse, overshoot=False)

    def step(self, dt: float) -> None:
        for spring in self.springs.values():
            spring.step(dt)
