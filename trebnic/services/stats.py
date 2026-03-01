import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

from models.entities import Task, Project


@dataclass
class DailyStats:
    """Stats for a single day."""
    date: date
    tracked_seconds: int
    estimated_done_seconds: int  # Estimated time for completed tasks
    estimated_pending_seconds: int  # Estimated time for pending tasks
    tasks_completed: int


@dataclass
class ProjectStats:
    """Stats for a single project."""
    project_id: Optional[str]
    project_name: str
    tracked_seconds: int
    tasks_completed: int
    tasks_pending: int


@dataclass
class OverallStats:
    """Overall user statistics."""
    total_tasks_completed: int
    total_tasks_pending: int
    total_time_tracked_seconds: int
    avg_estimation_accuracy: float  # percentage: actual/estimated * 100
    tasks_with_estimates: int
    # Placeholder for future: postponement stats
    # total_postponements: int = 0
    # avg_postponements_per_task: float = 0.0


class StatsService:
    """Service for calculating user statistics."""

    def calculate_overall_stats(
        self,
        tasks: List[Task],
        done_tasks: List[Task],
        time_entries: List[Dict],
    ) -> OverallStats:
        """Calculate overall statistics across all tasks."""
        total_completed = len(done_tasks)
        total_pending = len(tasks)

        # Calculate total time tracked from time entries
        total_tracked = 0
        for entry in time_entries:
            start = entry.get("start_time")
            end = entry.get("end_time")
            if start and end:
                start_dt = datetime.fromisoformat(start) if isinstance(start, str) else start
                end_dt = datetime.fromisoformat(end) if isinstance(end, str) else end
                total_tracked += int((end_dt - start_dt).total_seconds())

        # Calculate estimation accuracy from COMPLETED tasks only
        # Only consider done tasks that have both estimation and tracked time
        done_with_estimation = [t for t in done_tasks if t.estimated_seconds > 0]
        done_with_both = [t for t in done_with_estimation if t.spent_seconds > 0]

        if done_with_both:
            accuracies = []
            for t in done_with_both:
                # Accuracy as percentage: 100% means exact match
                # >100% means took longer, <100% means faster
                accuracy = (t.spent_seconds / t.estimated_seconds) * 100
                accuracies.append(accuracy)
            avg_accuracy = sum(accuracies) / len(accuracies)
        else:
            avg_accuracy = 0.0

        # Count tasks with estimates for display
        all_tasks = tasks + done_tasks
        tasks_with_estimation = [t for t in all_tasks if t.estimated_seconds > 0]

        return OverallStats(
            total_tasks_completed=total_completed,
            total_tasks_pending=total_pending,
            total_time_tracked_seconds=total_tracked,
            avg_estimation_accuracy=avg_accuracy,
            tasks_with_estimates=len(tasks_with_estimation),
        )

    def calculate_daily_stats(
        self,
        time_entries: List[Dict],
        done_tasks: List[Task],
        tasks: Optional[List[Task]] = None,
        days: int = 7,
        start_date: Optional[date] = None,
    ) -> List[DailyStats]:
        """Calculate stats for each day in a range.

        Args:
            time_entries: List of time entry dicts
            done_tasks: List of completed tasks
            tasks: Optional list of pending tasks
            days: Number of days to include
            start_date: Start date for the range (default: today - days + 1)
        """
        if start_date is None:
            # Default behavior: last N days ending today
            today = date.today()
            start_date = today - timedelta(days=days - 1)

        stats_by_date: Dict[date, DailyStats] = {}

        # Initialize all days with zero values
        for i in range(days):
            d = start_date + timedelta(days=i)
            stats_by_date[d] = DailyStats(
                date=d,
                tracked_seconds=0,
                estimated_done_seconds=0,
                estimated_pending_seconds=0,
                tasks_completed=0,
            )

        # Aggregate time entries by date
        for entry in time_entries:
            start = entry.get("start_time")
            end = entry.get("end_time")
            if start and end:
                start_dt = datetime.fromisoformat(start) if isinstance(start, str) else start
                end_dt = datetime.fromisoformat(end) if isinstance(end, str) else end
                entry_date = start_dt.date()

                if entry_date in stats_by_date:
                    duration = int((end_dt - start_dt).total_seconds())
                    stats_by_date[entry_date].tracked_seconds += duration

        # Count completed tasks by completion date (using due_date as proxy)
        # and aggregate estimated seconds for done tasks
        # TODO: Add completed_at field to Task model for accurate tracking
        for task in done_tasks:
            if task.due_date and task.due_date in stats_by_date:
                stats_by_date[task.due_date].tasks_completed += 1
                stats_by_date[task.due_date].estimated_done_seconds += task.estimated_seconds

        # Add estimated seconds from pending tasks with due dates
        if tasks:
            for task in tasks:
                if task.due_date and task.due_date in stats_by_date:
                    stats_by_date[task.due_date].estimated_pending_seconds += task.estimated_seconds

        # Return sorted by date (oldest first for chart display)
        return sorted(stats_by_date.values(), key=lambda s: s.date)

    def calculate_project_stats(
        self,
        tasks: List[Task],
        done_tasks: List[Task],
        projects: List[Project],
    ) -> List[ProjectStats]:
        """Calculate stats grouped by project."""
        # Create lookup for project names
        project_names = {p.id: p.name for p in projects}
        project_names[None] = "Unassigned"

        # Group tasks by project
        stats_by_project: Dict[Optional[str], ProjectStats] = {}

        all_tasks = tasks + done_tasks
        for task in all_tasks:
            pid = task.project_id
            if pid not in stats_by_project:
                stats_by_project[pid] = ProjectStats(
                    project_id=pid,
                    project_name=project_names.get(pid, "Unknown"),
                    tracked_seconds=0,
                    tasks_completed=0,
                    tasks_pending=0,
                )

            stats_by_project[pid].tracked_seconds += task.spent_seconds

        # Count completed vs pending
        for task in done_tasks:
            pid = task.project_id
            if pid in stats_by_project:
                stats_by_project[pid].tasks_completed += 1

        for task in tasks:
            pid = task.project_id
            if pid in stats_by_project:
                stats_by_project[pid].tasks_pending += 1

        return list(stats_by_project.values())

    def filter_by_project(
        self,
        tasks: List[Task],
        done_tasks: List[Task],
        time_entries: List[Dict],
        project_id: Optional[str],
    ) -> tuple:
        """Filter tasks and time entries by project.

        Returns (filtered_tasks, filtered_done_tasks, filtered_entries).
        If project_id is None, returns all data unfiltered.
        """
        if project_id is None:
            return tasks, done_tasks, time_entries

        filtered_tasks = [t for t in tasks if t.project_id == project_id]
        filtered_done = [t for t in done_tasks if t.project_id == project_id]

        # Get task IDs for this project
        task_ids = {t.id for t in filtered_tasks + filtered_done if t.id is not None}
        filtered_entries = [e for e in time_entries if e.get("task_id") in task_ids]

        return filtered_tasks, filtered_done, filtered_entries

    def calculate_completion_streak(self, done_tasks: List[Task]) -> int:
        """Calculate the longest streak of consecutive days with completed tasks.

        Returns the number of consecutive days where at least one task was completed.
        Uses task due_date as a proxy for completion date.
        """
        if not done_tasks:
            return 0

        # Collect all completion dates (using due_date as proxy)
        completion_dates = set()
        for task in done_tasks:
            if task.due_date:
                completion_dates.add(task.due_date)

        if not completion_dates:
            return 0

        # Sort dates
        sorted_dates = sorted(completion_dates)

        # Find longest consecutive streak
        longest_streak = 1
        current_streak = 1

        for i in range(1, len(sorted_dates)):
            # Check if this date is consecutive to previous
            if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 1

        return longest_streak

    def export_to_json(
        self,
        tasks: List[Task],
        done_tasks: List[Task],
        projects: List[Project],
        time_entries: List[Dict],
    ) -> str:
        """Export all stats data to JSON format."""
        # Calculate all stats
        overall = self.calculate_overall_stats(tasks, done_tasks, time_entries)
        project_stats = self.calculate_project_stats(tasks, done_tasks, projects)
        daily_stats = self.calculate_daily_stats(time_entries, done_tasks, tasks, days=30)
        streak = self.calculate_completion_streak(done_tasks)

        export_data: Dict[str, Any] = {
            "export_date": datetime.now().isoformat(),
            "overall_stats": {
                "tasks_completed": overall.total_tasks_completed,
                "tasks_pending": overall.total_tasks_pending,
                "total_time_tracked_seconds": overall.total_time_tracked_seconds,
                "avg_estimation_accuracy_percent": round(overall.avg_estimation_accuracy, 2),
                "tasks_with_estimates": overall.tasks_with_estimates,
                "longest_completion_streak_days": streak,
            },
            "projects": [
                {
                    "name": ps.project_name,
                    "tracked_seconds": ps.tracked_seconds,
                    "tasks_completed": ps.tasks_completed,
                    "tasks_pending": ps.tasks_pending,
                }
                for ps in project_stats
            ],
            "daily_stats": [
                {
                    "date": ds.date.isoformat(),
                    "tracked_seconds": ds.tracked_seconds,
                    "estimated_done_seconds": ds.estimated_done_seconds,
                    "estimated_pending_seconds": ds.estimated_pending_seconds,
                    "tasks_completed": ds.tasks_completed,
                }
                for ds in daily_stats
            ],
            "tasks": [
                {
                    "title": t.title,
                    "spent_seconds": t.spent_seconds,
                    "estimated_seconds": t.estimated_seconds,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "completed": False,
                }
                for t in tasks
            ]
            + [
                {
                    "title": t.title,
                    "spent_seconds": t.spent_seconds,
                    "estimated_seconds": t.estimated_seconds,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "completed": True,
                }
                for t in done_tasks
            ],
        }

        return json.dumps(export_data, indent=2, ensure_ascii=False)

    # =========================================================================
    # Placeholder methods for future implementation
    # =========================================================================

    def calculate_weekly_stats(
        self,
        time_entries: List[Dict],
        done_tasks: List[Task],
        weeks: int = 4,
    ) -> List[DailyStats]:
        """Calculate stats aggregated by week.

        TODO: Implement weekly aggregation view.
        """
        # Placeholder - return empty list
        return []

    def calculate_estimation_breakdown(
        self,
        tasks: List[Task],
        done_tasks: List[Task],
    ) -> Dict:
        """Calculate detailed estimation vs actual breakdown.

        TODO: Implement detailed breakdown showing:
        - Tasks completed faster than estimated
        - Tasks that took longer
        - Distribution chart data
        """
        # Placeholder
        return {
            "faster_count": 0,
            "slower_count": 0,
            "on_time_count": 0,
            "distribution": [],
        }


# Singleton instance
stats_service = StatsService()
