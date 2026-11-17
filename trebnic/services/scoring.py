"""Derived points: time entries remain the source of truth, never award twice."""
from dataclasses import dataclass
from math import floor


def base_points(task):
    seconds = task.initial_estimated_seconds
    if seconds is None:
        seconds = task.estimated_seconds
    return max(0, seconds) / 900


def completion_points(task):
    return base_points(task) * (1 - min(5, max(0, task.postponements)) * .1)


@dataclass(frozen=True)
class Progress:
    completion: float
    effort: float
    penalties: float

    @property
    def score(self):
        return self.completion + self.effort - self.penalties

    @property
    def xp(self):
        return self.completion + self.effort

    @property
    def level(self):
        return 1 + floor(self.xp / 50)

    @property
    def fraction(self):
        return (self.xp % 50) / 50


def progress(tasks, closed):
    all_tasks = {t.id if t.id is not None else id(t): t for t in [*tasks, *closed]}
    return Progress(
        completion=sum(completion_points(t) for t in closed if not t.is_failed and not t.points_excluded),
        effort=sum(max(0, t.spent_seconds - t.points_time_baseline_seconds) / 3600 for t in all_tasks.values()),
        penalties=sum(.9 * base_points(t) for t in closed if t.is_failed and not t.points_excluded),
    )
