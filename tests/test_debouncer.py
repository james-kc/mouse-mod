"""Unit tests for the pure debounce logic.

A FakeClock drives time so event streams (including realistic bouncing-switch
streams) are fully deterministic.
"""

import pytest

from debouncer import BUTTONS, LEFT, MIDDLE, RIGHT, Debouncer


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds: float):
        self.now += seconds
        return self.now


@pytest.fixture
def setup():
    clock = FakeClock()
    deb = Debouncer(clock=clock)
    return clock, deb


def click(clock, deb, button, press_ms=5, release_after=True):
    """Simulate a clean click: down, optional gap, up."""
    out = [deb.handle_event(button, True)]
    if release_after:
        clock.advance(press_ms / 1000.0)
        out.append(deb.handle_event(button, False))
    return out


def test_single_click_passes(setup):
    clock, deb = setup
    assert click(clock, deb, MIDDLE) == [False, False]


def test_bounce_is_suppressed(setup):
    clock, deb = setup
    clock.advance(1.0)
    # First click passes fully.
    assert click(clock, deb, MIDDLE) == [False, False]
    # Faulty switch re-fires 8 ms later: whole phantom click swallowed.
    clock.advance(0.008)
    assert click(clock, deb, MIDDLE) == [True, True]


def test_threshold_boundary(setup):
    clock, deb = setup
    deb.set_button(MIDDLE, True, 50.0)
    clock.advance(1.0)
    assert deb.handle_event(MIDDLE, True) is False
    deb.handle_event(MIDDLE, False)
    clock.advance(0.050)  # exactly at threshold -> allowed (suppression is <)
    assert deb.handle_event(MIDDLE, True) is False


def test_slow_double_click_passes(setup):
    clock, deb = setup
    clock.advance(1.0)
    assert click(clock, deb, LEFT) == [False, False]
    clock.advance(0.3)  # human double-click speed >> 50 ms
    assert click(clock, deb, LEFT) == [False, False]


def test_up_without_swallowed_down_passes(setup):
    clock, deb = setup
    # App started mid-press, or hook missed the down: must not eat the up.
    assert deb.handle_event(LEFT, False) is False


def test_buttons_are_independent(setup):
    clock, deb = setup
    clock.advance(1.0)
    click(clock, deb, LEFT)
    clock.advance(0.010)
    # Rapid click on a *different* button must not be treated as a bounce.
    assert click(clock, deb, RIGHT) == [False, False]


def test_per_button_disable(setup):
    clock, deb = setup
    deb.set_button(LEFT, False, 50.0)  # debounce off for LEFT only
    clock.advance(1.0)
    click(clock, deb, LEFT)
    clock.advance(0.005)
    assert click(clock, deb, LEFT) == [False, False]
    # MIDDLE still debounced.
    clock.advance(1.0)
    click(clock, deb, MIDDLE)
    clock.advance(0.005)
    assert click(clock, deb, MIDDLE) == [True, True]


def test_master_disable_passes_everything(setup):
    clock, deb = setup
    deb.set_master(False)
    clock.advance(1.0)
    click(clock, deb, MIDDLE)
    clock.advance(0.002)
    assert click(clock, deb, MIDDLE) == [False, False]


def test_disable_while_press_swallowed_keeps_os_consistent(setup):
    """If debounce is disabled mid-bounce, the next up must still pass
    cleanly (state reset on reconfigure)."""
    clock, deb = setup
    clock.advance(1.0)
    click(clock, deb, MIDDLE)
    clock.advance(0.005)
    assert deb.handle_event(MIDDLE, True) is True  # bounced down
    deb.set_button(MIDDLE, True, 0.0)              # user tweakes settings
    assert deb.handle_event(MIDDLE, False) is False  # up not orphaned


def test_double_bounce_suppressed(setup):
    clock, deb = setup
    clock.advance(1.0)
    click(clock, deb, MIDDLE)
    for _ in range(3):  # switch chatters 3 extra times
        clock.advance(0.006)
        assert click(clock, deb, MIDDLE) == [True, True]


def test_stats_counting(setup):
    clock, deb = setup
    clock.advance(1.0)
    click(clock, deb, MIDDLE)          # 2 received, 0 suppressed
    clock.advance(0.008)
    click(clock, deb, MIDDLE)          # 2 received, 2 suppressed
    stats = deb.get_stats()
    received, suppressed = stats[MIDDLE]
    assert received == 4 and suppressed == 2
    assert stats[LEFT] == (0, 0)


def test_reset_stats(setup):
    clock, deb = setup
    click(clock, deb, MIDDLE)
    deb.reset_stats()
    assert all(v == (0, 0) for v in deb.get_stats().values())


def test_config_roundtrip(setup):
    clock, deb = setup
    deb.set_master(False)
    deb.set_button(MIDDLE, False, 120.0)
    data = deb.dump_config()

    deb2 = Debouncer(clock=clock)
    deb2.load_config(data)
    assert deb2.master_enabled is False
    assert deb2.config[MIDDLE].enabled is False
    assert deb2.config[MIDDLE].threshold_ms == 120.0
    assert deb2.config[LEFT].enabled is True  # untouched defaults


def test_load_config_tolerates_garbage(setup):
    clock, deb = setup
    deb.load_config({"master_enabled": "yes", "buttons": {
        MIDDLE: {"enabled": None, "threshold_ms": "banana"}}})
    assert deb.config[MIDDLE].threshold_ms > 0  # fell back to default


def test_stats_exist_for_all_buttons(setup):
    clock, deb = setup
    assert set(deb.get_stats()) == set(BUTTONS)


def test_invalid_button_rejected(setup):
    clock, deb = setup
    with pytest.raises(ValueError):
        deb.set_button("hyper-wheel", True, 10)


def test_negative_threshold_rejected(setup):
    clock, deb = setup
    with pytest.raises(ValueError):
        deb.set_button(MIDDLE, True, -1)
