"""One activation per continuous dwell, with explicit departure to rearm."""


class DwellTracker:
    def __init__(self, duration=1.0, max_gap=0.3):
        self.duration = duration
        self.max_gap = max_gap
        self.reset()

    def reset(self):
        self.locked = None
        self.cancel()

    def cancel(self):
        # Tracking loss cancels progress, but does not rearm an activated button.
        self.target = None
        self.started = None
        self.last_time = None
        self.progress = 0.0

    def observe(self, target, timestamp):
        if self.last_time is not None and (timestamp <= self.last_time or timestamp - self.last_time > self.max_gap):
            self.cancel()
        if target != self.locked:
            self.locked = None
        if target is None or target == self.locked:
            self.cancel()
            return False
        if target != self.target:
            self.target = target
            self.started = timestamp
        self.last_time = timestamp
        self.progress = min(1.0, (timestamp - self.started) / self.duration)
        if self.progress >= 1:
            self.locked = target
            return True
        return False
