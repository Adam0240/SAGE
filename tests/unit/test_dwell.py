from TouchControls.dwell import DwellTracker


def feed(tracker, target, start, count=11):
    return [tracker.observe(target, round(start + i * 0.1, 3)) for i in range(count)]


def test_one_second_activates_once_until_departure():
    dwell = DwellTracker()
    assert feed(dwell, "button", 0) == [False] * 10 + [True]
    assert not any(feed(dwell, "button", 1.1, 20))
    dwell.observe(None, 3.2)
    assert feed(dwell, "button", 3.3)[-1]


def test_changing_targets_and_tracking_gaps_restart_progress():
    dwell = DwellTracker()
    feed(dwell, "one", 0, 8)
    assert not dwell.observe("two", 0.8)
    assert dwell.progress == 0
    feed(dwell, "two", 0.9, 5)
    assert not dwell.observe("two", 2)
    assert dwell.progress == 0
    dwell.cancel()
    assert dwell.progress == 0


def test_tracking_loss_does_not_rearm_an_already_activated_button():
    dwell = DwellTracker()
    assert feed(dwell, "one", 0)[-1]
    dwell.cancel()
    assert not any(feed(dwell, "one", 3))
    dwell.reset()
    assert feed(dwell, "one", 5)[-1]
