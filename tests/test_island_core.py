"""D-045: the island's spring maths, state machine (priorities, interruptions, banner queue,
timeouts) and geometry (capsule radius, split layout, click-through region)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRectF

from wisp.system.media import MediaState
from wisp.ui.island import geometry
from wisp.ui.island.machine import TIERS, IslandStateMachine, Presentation
from wisp.ui.island.spring import Spring, SpringSet, damped
from wisp.ui.theme import ISLAND

FRAME = 1 / 60


def run(spring: Spring, seconds: float, dt: float = FRAME) -> list[float]:
    values = []
    for _ in range(round(seconds / dt)):
        spring.step(dt)
        values.append(spring.value)
    return values


# ----- springs ------------------------------------------------------------------------------------
@pytest.mark.parametrize("tokens", [ISLAND.expand, ISLAND.collapse, ISLAND.small])
def test_spring_settles_within_half_a_second(tokens):
    spring = Spring(32.0)
    spring.retarget(580.0, tokens, overshoot=True)
    run(spring, 0.5)
    assert spring.settled and spring.value == 580.0 and spring.velocity == 0.0


def test_expand_overshoots_a_few_pixels_then_settles():
    spring = Spring(32.0)
    spring.retarget(580.0, ISLAND.expand, overshoot=True)
    values = run(spring, 0.8)
    peak = max(values)
    assert 580.0 < peak <= 588.0  # a few pixels past the target
    assert values[-1] == 580.0


def test_collapse_never_overshoots_even_when_interrupted_at_speed():
    spring = Spring(580.0)
    spring.retarget(36.0, ISLAND.collapse, overshoot=False)
    values = run(spring, 0.6)
    assert min(values) >= 36.0 and values[-1] == 36.0
    # Moving fast towards the target when the collapse starts would carry a plain
    # critically damped spring past it; the clamp stops it at the target.
    fast = Spring(300.0, velocity=-6000.0)
    fast.retarget(36.0, ISLAND.collapse, overshoot=False)
    assert min(run(fast, 0.6)) >= 36.0


def test_retarget_mid_flight_has_no_jump():
    spring = Spring(32.0)
    spring.retarget(580.0, ISLAND.expand, overshoot=True)
    run(spring, 0.12)
    value, velocity = spring.value, spring.velocity
    assert 32.0 < value < 580.0 and velocity > 0
    spring.retarget(36.0, ISLAND.collapse, overshoot=False)
    assert (spring.value, spring.velocity) == (value, velocity)  # same position and speed
    steps = run(spring, 0.5)
    assert steps[0] > value  # momentum: it keeps moving outwards for a moment, then turns
    assert min(steps) >= 36.0 and steps[-1] == 36.0
    # No frame moves faster than a plain collapse from the fully expanded size does.
    plain = Spring(580.0)
    plain.retarget(36.0, ISLAND.collapse, overshoot=False)
    plain_steps = run(plain, 0.5)

    def fastest(values, start):
        return max(abs(b - a) for a, b in zip([start, *values], values, strict=False))

    assert fastest(steps, value) <= fastest(plain_steps, 580.0)


def test_spring_is_independent_of_frame_rate():
    a, b = Spring(0.0), Spring(0.0)
    for spring in (a, b):
        spring.retarget(100.0, ISLAND.expand)
    run(a, 0.2, dt=1 / 60)
    run(b, 0.2, dt=1 / 30)
    assert a.value == pytest.approx(b.value, abs=1e-6)


def test_damped_matches_the_differential_equation():
    k, ratio, x0, v0 = 380.0, 0.82, 10.0, -3.0
    c = 2 * ratio * k ** 0.5
    x, v = x0, v0
    for _ in range(100_000):  # tiny explicit steps over 0.1 s
        a = -k * x - c * v
        x, v = x + v * 1e-6, v + a * 1e-6
    exact = damped(x0, v0, k, ratio, 0.1)
    assert exact[0] == pytest.approx(x, rel=1e-3) and exact[1] == pytest.approx(v, rel=1e-3)
    for ratio in (1.0, 1.4):  # critical and over-damped branches start where they should
        assert damped(x0, v0, k, ratio, 0.0) == pytest.approx((x0, v0))


def test_spring_set_picks_constants_by_direction():
    springs = SpringSet(w=180.0, h=32.0)
    springs.retarget(w=720.0, h=36.0)
    assert springs.springs["w"].overshoot
    assert springs.springs["w"].stiffness == ISLAND.expand.stiffness
    assert springs.springs["h"].stiffness == ISLAND.small.stiffness  # a small change
    springs.retarget(w=180.0)
    assert not springs.springs["w"].overshoot
    springs.retarget(animate=False, w=300.0, h=36.0)
    assert springs["w"] == 300.0 and springs.settled


# ----- state machine ------------------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def machine(clock):
    return IslandStateMachine(clock=clock)


PLAYING = MediaState(True, "Blue in Green", "Miles Davis", "Spotify", True, 30, 337)


def test_priority_order_is_defined_once():
    assert TIERS == ("voice", "banner", "timer", "music", "idle")


def test_voice_beats_timer_beats_music_and_split_shows_two(machine, clock):
    assert machine.presentation == Presentation("idle")
    machine.set_music(PLAYING)
    assert machine.presentation.mode == "activity"
    assert machine.presentation.main.kind == "music" and machine.presentation.secondary is None
    machine.set_countdown("Call the bank", clock.now + 300)
    p = machine.presentation
    assert (p.main.kind, p.secondary.kind) == ("countdown", "music")
    machine.set_voice("listening", "Listening…")
    p = machine.presentation
    assert (p.main.kind, p.secondary.kind) == ("listening", "countdown")  # split: two at once
    assert p.main.meter == "mic"
    machine.set_voice("idle")
    machine.set_countdown(None)
    assert machine.presentation.main.kind == "music"
    machine.set_music(MediaState(True, "Blue in Green", playing=False))
    assert machine.presentation.mode == "idle"  # paused media is not live


def test_voice_flow_idle_listening_thinking_speaking_idle(machine):
    kinds = []
    machine.subscribe(lambda p: kinds.append(p.main.kind if p.main else p.mode))
    for state in ("listening", "thinking", "speaking", "idle"):
        machine.set_voice(state, state)
    assert kinds == ["listening", "thinking", "speaking", "idle"]
    machine.set_voice("error", "Google rejected this API key")
    assert machine.presentation.mode == "idle"  # errors come as banners, not activities


def test_banner_shows_holds_and_returns_by_itself(machine, clock):
    machine.set_music(PLAYING)
    banner = machine.post("Routine done: Morning", "✓ Opened Spotify", "check", "success")
    assert machine.presentation == Presentation("banner", banner=banner)  # banner > music
    assert machine.next_deadline() == pytest.approx(clock.now + ISLAND.banner_hold_ms / 1000)
    clock.now += ISLAND.banner_hold_ms / 1000 - 0.1
    machine.update()
    assert machine.presentation.mode == "banner"
    clock.now += 0.2
    machine.update()
    assert machine.presentation.main.kind == "music"


def test_banners_queue_one_at_a_time_and_coalesce(machine, clock):
    first = machine.post("Reminder", "Call the bank")
    machine.post("Reminder", "Water the plants")
    machine.post("Reminder", "Water the plants")  # the same again: refreshed, not repeated
    assert machine.presentation.banner == first
    machine.dismiss()
    assert machine.presentation.banner.line == "Water the plants"
    machine.dismiss()
    assert machine.presentation.mode == "idle"


def test_queue_keeps_only_the_newest(machine):
    machine.set_voice("listening")
    for n in range(ISLAND.banner_queue + 3):
        machine.post("Note", str(n))
    machine.set_voice("idle")
    assert machine.presentation.banner.line == "3"  # 0–2 were dropped


def test_active_voice_interrupts_a_banner_which_resumes_afterwards(machine, clock):
    banner = machine.post("Reminder", "Call the bank")
    clock.now += 2.5
    machine.set_voice("listening")
    assert machine.presentation.main.kind == "listening"  # voice > banner
    clock.now += 5
    machine.set_voice("idle")
    assert machine.presentation.banner == banner  # back, and its hold starts over
    clock.now += ISLAND.banner_hold_ms / 1000 - 0.5
    machine.update()
    assert machine.presentation.mode == "banner"


def test_stale_banners_are_dropped(machine, clock):
    machine.set_voice("speaking")
    machine.post("Reminder", "Old news")
    clock.now += ISLAND.banner_max_age_ms / 1000 + 1
    machine.set_voice("idle")
    assert machine.presentation.mode == "idle"


def test_hover_holds_a_banner_and_adds_time_after_leaving(machine, clock):
    machine.post("Routine done", "All good")
    machine.set_hover(True)
    clock.now += 60
    machine.update()
    assert machine.presentation.mode == "banner"
    assert machine.next_deadline() is None  # nothing times out while hovered
    machine.set_hover(False)
    clock.now += ISLAND.banner_hover_extra_ms / 1000 - 0.1
    machine.update()
    assert machine.presentation.mode == "banner"
    clock.now += 0.2
    machine.update()
    assert machine.presentation.mode == "idle"


def test_short_status_times_out(machine, clock):
    machine.show_status("dictation", "Dictating…", "success", "dictation")
    assert machine.presentation.main.kind == "dictation"
    machine.show_status("status", "Inserted 12 words", "success", ms=1500)
    assert machine.next_deadline() == pytest.approx(clock.now + 1.5)
    clock.now += 1.6
    machine.update()
    assert machine.presentation.mode == "idle"


def test_expanded_wins_and_banners_wait(machine, clock):
    machine.expand()
    machine.set_voice("speaking", "It's 3 pm")
    machine.post("Reminder", "Call the bank")
    p = machine.presentation
    assert p.mode == "expanded" and p.main.kind == "speaking" and p.banner is None
    machine.set_voice("idle")
    machine.collapse()
    assert machine.presentation.mode == "banner"


def test_idle_island_slides_away_after_the_delay_and_reveal_brings_it_back(machine, clock):
    machine.set_autohide(True, 6000)
    clock.now += 5.9
    machine.update()
    assert machine.presentation.mode == "idle"
    assert machine.next_deadline() == pytest.approx(clock.now + 0.1)
    clock.now += 0.2
    machine.update()
    assert machine.presentation.mode == "away"
    machine.reveal()  # the pointer rested in the top-centre zone
    assert machine.presentation.mode == "idle"
    clock.now += 5.9
    machine.update()
    assert machine.presentation.mode == "idle"  # the quiet spell started over at the reveal
    machine.set_hover(True)
    clock.now += 60
    machine.update()
    assert machine.presentation.mode == "idle"  # never while the pointer is on it
    machine.set_hover(False)
    clock.now += 6.1
    machine.update()
    assert machine.presentation.mode == "away"  # the delay after the pointer leaves


def test_never_hides_while_something_is_going_on(machine, clock):
    machine.set_autohide(True, 3000)

    def stays_after(seconds=30.0):
        clock.now += seconds
        machine.update()
        return machine.presentation.mode not in ("away",)

    machine.set_voice("listening")
    assert stays_after()
    machine.set_voice("idle")
    machine.show_status("dictation", "Dictating…", "success", "dictation")
    assert stays_after()
    machine.clear_status()
    machine.set_countdown("Call the bank", 1.8e9)
    assert stays_after()
    machine.set_countdown(None)
    machine.set_confirming(True)
    assert stays_after()
    machine.set_confirming(False)
    machine.expand()
    assert stays_after()
    machine.collapse()
    machine.set_voice("speaking")
    machine.post("Reminder", "Call the bank")  # queued behind voice
    machine.set_voice("idle")
    machine.set_hover(True)  # keeps the banner up
    assert stays_after() and machine.presentation.mode == "banner"
    machine.set_hover(False)
    clock.now += 2.0
    machine.update()
    assert machine.presentation.mode == "idle"  # the banner left; a new quiet spell starts
    assert stays_after(2.9)
    assert not stays_after(0.2)


def test_activity_reveals_instantly(machine, clock):
    machine.set_autohide(True, 3000)
    clock.now += 4
    machine.update()
    assert machine.presentation.mode == "away"
    machine.set_voice("listening")
    assert machine.presentation.main.kind == "listening"
    machine.set_voice("idle")
    clock.now += 4
    machine.update()
    machine.post("Reminder", "Stretch")
    assert machine.presentation.mode == "banner"


def test_music_keeps_it_visible_unless_switched_off(machine, clock):
    machine.set_autohide(True, 3000)
    machine.set_music(PLAYING)
    clock.now += 30
    machine.update()
    assert machine.presentation.main.kind == "music"
    machine.set_autohide(True, 3000, keep_for_music=False)
    clock.now += 3.1
    machine.update()
    assert machine.presentation.mode == "away"
    machine.reveal()
    assert machine.presentation.main.kind == "music"  # revealed: shows what's playing


def test_full_screen_doesnt_bring_a_hidden_island_back(machine, clock):
    machine.set_autohide(True, 3000)
    clock.now += 4
    machine.update()
    machine.set_hidden(True)
    assert machine.presentation.mode == "hidden"
    clock.now += 60
    machine.set_hidden(False)
    assert machine.presentation.mode == "away"  # straight back, no surprise reappearance


def test_autohide_off_never_hides(machine, clock):
    clock.now += 3600
    machine.update()
    assert machine.presentation.mode == "idle"


def test_fullscreen_hides_everything_and_collapses(machine):
    machine.expand()
    machine.set_hidden(True)
    assert machine.presentation.mode == "hidden" and not machine.expanded
    machine.set_hidden(False)
    assert machine.presentation.mode == "idle"


def test_content_key_ignores_text_changes(machine):
    machine.set_voice("speaking", "It's")
    key = machine.presentation.content_key
    machine.set_voice("speaking", "It's 3 pm")
    assert machine.presentation.content_key == key


# ----- geometry -----------------------------------------------------------------------------------
def test_targets_per_state():
    machine = IslandStateMachine()
    assert geometry.target_for(machine.presentation) == geometry.ShapeTarget(*ISLAND.idle)
    hover = geometry.target_for(machine.presentation, hover=True)
    assert hover.width == pytest.approx(ISLAND.idle[0] * 1.04)
    machine.set_music(PLAYING)
    machine.set_voice("listening")
    split = geometry.target_for(machine.presentation)
    assert split.split == ISLAND.split_diameter and split.gap == ISLAND.split_gap
    machine.expand()
    assert geometry.target_for(machine.presentation) == geometry.ShapeTarget(*ISLAND.expanded)


def test_corner_radius_is_a_capsule_when_compact():
    for height in (5, 32, 36, 40, 52):
        assert geometry.corner_radius(height) == min(height / 2, ISLAND.expanded_radius)
    assert geometry.corner_radius(580) == ISLAND.expanded_radius


def test_canvas_fits_every_shape_with_overshoot_and_shadow():
    width, height = geometry.canvas_size()
    assert width >= ISLAND.expanded[0] * 1.02 + 2 * ISLAND.shadow_margin
    assert height >= ISLAND.top + ISLAND.expanded[1] * 1.02 + ISLAND.shadow_margin


def test_split_circle_sits_beside_the_pill_and_the_group_is_centred():
    main, circle = geometry.shape_rects(800, 6, 300, 36, 36, 8)
    assert circle.left() == main.right() + 8 and circle.center().y() == main.center().y()
    assert (main.left() + circle.right()) / 2 == pytest.approx(400)
    assert geometry.shape_rects(800, 6, 300, 36, 0.4, 1)[1] is None  # not yet visible


def test_input_region_is_the_visible_shape_only():
    main, circle = geometry.shape_rects(800, 6, 300, 36, 36, 8)
    region = geometry.input_region(main, circle)
    inside = [main.center(), QRectF(main).adjusted(18, 4, -18, -4).topLeft(), circle.center()]
    for point in inside:
        assert region.contains(point.toPoint())
    beside = [QPoint(int(main.left()) - 6, 24),  # just left of the pill
              QPoint(int(main.left()) + 1, 7),  # inside the bounding box, outside the corner
              QPoint(int(main.right()) + 4, 24),  # the gap between pill and circle
              QPoint(400, int(main.bottom()) + 4),  # just below
              QPoint(int(circle.right()) + 6, 24)]
    for point in beside:
        assert not region.contains(point), point


def test_input_region_tracks_the_animated_shape():
    small = geometry.input_region(QRectF(310, 6, 180, 32))
    large = geometry.input_region(QRectF(40, 6, 720, 580))
    probe = QPoint(100, 300)
    assert not small.contains(probe) and large.contains(probe)
    assert large.boundingRect().width() == 720 + 2 * geometry.AA_MARGIN


# ----- full-screen detection and countdowns -------------------------------------------------------
def test_fullscreen_decision():
    from wisp.winapi.fullscreen import (
        QUNS_BUSY,
        QUNS_PRESENTATION_MODE,
        QUNS_RUNNING_D3D_FULL_SCREEN,
        decide,
    )

    monitor = (0, 0, 2560, 1440)
    covering = (-1, -1, 2561, 1441)
    windowed = (100, 100, 1200, 900)
    accepts = 5
    assert decide(QUNS_RUNNING_D3D_FULL_SCREEN, False, None, monitor, False, False)
    assert decide(QUNS_PRESENTATION_MODE, False, None, monitor, False, False)
    assert decide(accepts, True, covering, monitor, False, False)  # borderless full screen
    assert decide(QUNS_BUSY, True, covering, monitor, False, False)
    assert not decide(QUNS_BUSY, False, covering, monitor, False, False)  # another monitor
    assert not decide(accepts, True, windowed, monitor, False, False)
    assert not decide(accepts, True, covering, monitor, True, False)  # maximized, not full screen
    assert not decide(accepts, True, covering, monitor, False, True)  # desktop, taskbar or Wisp


def test_countdown_picks_the_soonest_within_ten_minutes():
    from datetime import datetime, timedelta

    from wisp.ui.island.machine import pick_countdown

    now = datetime(2026, 10, 14, 14, 50).astimezone()
    items = [("Later", now + timedelta(minutes=30)), ("Call the bank", now + timedelta(minutes=8)),
             ("Water plants", now + timedelta(minutes=4)), ("Past", now - timedelta(minutes=1)),
             ("No time", None)]
    title, due = pick_countdown(items, now)
    assert title == "Water plants" and due == (now + timedelta(minutes=4)).timestamp()
    assert pick_countdown(items[:1], now) is None


def test_countdown_text():
    from wisp.ui.island.content import countdown_text

    assert countdown_text(1000 + 272, 1000) == "4:32"
    assert countdown_text(1000 + 3725, 1000) == "1:02:05"
    assert countdown_text(990, 1000) == "0:00"


# ----- reveal zone --------------------------------------------------------------------------------
@pytest.mark.parametrize("screen", [
    (0, 0, 1920, 1080),  # 100 %
    (0, 0, 2194, 1234),  # 175 % on a 3840 × 2160 panel
    (-1280, 0, 1280, 1024),  # a second display to the left
    (1920, -200, 1707, 960),  # a display above-right, at 150 % of 2560 × 1440
])
def test_hot_zone_is_the_top_centre_edge_of_each_display(screen):
    from PySide6.QtCore import QRect

    from wisp.ui.island.reveal import hot_zone, in_zone

    rect = QRect(*screen)
    zone = hot_zone(rect)
    assert zone.width() == ISLAND.idle[0] + 2 * ISLAND.reveal_margin
    assert zone.height() == ISLAND.reveal_height and zone.top() == rect.top()
    assert abs(zone.center().x() - rect.center().x()) <= 1
    centre = QPoint(rect.center().x(), rect.top())
    assert in_zone(centre, zone)
    assert in_zone(QPoint(zone.right(), rect.top() + ISLAND.reveal_height - 1), zone)
    assert not in_zone(QPoint(zone.right() + 1, rect.top()), zone)  # beside: browser tabs
    assert not in_zone(QPoint(centre.x(), rect.top() + ISLAND.reveal_height), zone)  # below


def test_hot_zone_keeps_its_size_on_screen_at_any_scaling():
    """Device-independent pixels: the zone covers the same physical inches at every scale."""
    from PySide6.QtCore import QRect

    from wisp.ui.island.reveal import hot_zone

    for scale in (1.0, 1.25, 1.5, 1.75, 2.0):
        logical = QRect(0, 0, round(3840 / scale), round(2160 / scale))
        zone = hot_zone(logical)
        physical_width = zone.width() * scale
        assert physical_width == pytest.approx((ISLAND.idle[0] + 80) * scale)


def test_dwell_needs_a_short_rest_in_the_zone():
    from wisp.ui.island.reveal import Dwell

    dwell = Dwell(150)
    assert not dwell.update(True, 10.00)
    assert not dwell.update(True, 10.14)
    assert dwell.update(True, 10.15)
    dwell.reset()
    assert not dwell.update(True, 20.0)
    assert not dwell.update(False, 20.1)  # passing over (browser tabs): starts again
    assert not dwell.update(True, 20.2)
    assert not dwell.update(True, 20.3)
    assert dwell.update(True, 20.36)
