from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# Maps time_of_day labels to (start_hour, end_hour) in 24h format
TIME_RANGES: dict[str, tuple[int, int]] = {
    "morning":   (6,  12),
    "afternoon": (12, 17),
    "evening":   (17, 21),
    "any":       (6,  21),
}

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

VALID_FREQUENCIES = {"once", "daily", "weekly"}

EDITABLE_FIELDS = {"title", "duration_minutes", "priority", "time_of_day", "completed", "frequency"}

logger = logging.getLogger(__name__)


@dataclass
class Owner:
    name: str
    available_hours: float
    wake_time: str          # e.g. "7:00 AM"
    task_buffer_minutes: int = 5
    pets: list[Pet] = field(default_factory=list)

    def __post_init__(self):
        """Validate owner fields after dataclass construction.

        Raises ValueError early so bad data is caught at creation time
        rather than silently producing a broken schedule later.
        """
        if not (0 < self.available_hours <= 16):
            logger.warning("Invalid available_hours=%.1f for owner '%s'", self.available_hours, self.name)
            raise ValueError("available_hours must be between 0 and 16")
        if not (0 <= self.task_buffer_minutes <= 30):
            logger.warning("Invalid task_buffer_minutes=%d for owner '%s'", self.task_buffer_minutes, self.name)
            raise ValueError("task_buffer_minutes must be between 0 and 30")

    def filter_tasks(
        self,
        pet_name: str | None = None,
        completed: bool | None = None,
    ) -> list[tuple[str, Task]]:
        """Return (pet_name, task) pairs filtered by pet name and/or completion status.

        Args:
            pet_name:  Only include tasks belonging to this pet. None = all pets.
            completed: True = done tasks only, False = pending only, None = both.
        """
        results = []
        for pet in self.pets:
            if pet_name is not None and pet.name != pet_name:
                continue
            for task in pet.tasks.values():
                if completed is not None and task.completed != completed:
                    continue
                results.append((pet.name, task))
        return results


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: str       # "low" | "medium" | "high"
    time_of_day: str    # "morning" | "afternoon" | "evening" | "any"
    frequency: str = "once"   # "once" | "daily" | "weekly"
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    completed: bool = False

    def edit(self, field: str, value) -> None:
        """Validate and update a single editable field on this task."""
        if field not in EDITABLE_FIELDS:
            raise ValueError(f"'{field}' is not an editable field. Choose from: {EDITABLE_FIELDS}")
        if field == "priority" and value not in PRIORITY_ORDER:
            raise ValueError(f"priority must be 'low', 'medium', or 'high', got '{value}'")
        if field == "time_of_day" and value not in TIME_RANGES:
            raise ValueError(f"time_of_day must be one of {list(TIME_RANGES)}, got '{value}'")
        if field == "duration_minutes" and (not isinstance(value, int) or value <= 0):
            raise ValueError(f"duration_minutes must be a positive integer, got {value!r}")
        if field == "completed" and not isinstance(value, bool):
            raise ValueError(f"completed must be True or False, got {value!r}")
        if field == "frequency" and value not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of {list(VALID_FREQUENCIES)}, got '{value}'")
        setattr(self, field, value)

    def mark_complete(self) -> None:
        """Mark this task as done so the scheduler skips it."""
        self.completed = True

    def next_occurrence(self) -> Task | None:
        """Return a fresh, uncompleted copy of this task for the next recurrence.

        Returns None for one-time tasks so callers can check with a simple truthiness test.
        The new instance gets a brand-new task_id so it is tracked independently.
        """
        if self.frequency == "once":
            return None
        return Task(
            title=self.title,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            time_of_day=self.time_of_day,
            frequency=self.frequency,
            # task_id auto-generates a new UUID; completed defaults to False
        )


@dataclass
class PlanEntry:
    task: Task
    start_time: str  # e.g. "8:00 AM"
    reason: str


@dataclass
class Pet:
    name: str
    species: str
    owner: Owner
    tasks: dict[str, Task] = field(default_factory=dict)

    def add_task(self, task: Task) -> None:
        """Add a task to this pet's task dict (keyed by task_id)."""
        self.tasks[task.task_id] = task
        logger.info("Added task '%s' (%s priority, %s) to %s", task.title, task.priority, task.frequency, self.name)

    def remove_task(self, task_id: str) -> None:
        """Remove a task by its unique ID in O(1), raising ValueError if not found."""
        if task_id not in self.tasks:
            logger.warning("Tried to remove unknown task_id '%s' from %s", task_id, self.name)
            raise ValueError(f"No task with id '{task_id}' found for {self.name}")
        title = self.tasks[task_id].title
        del self.tasks[task_id]
        logger.info("Removed task '%s' from %s", title, self.name)

    def complete_task(self, task_id: str) -> Task | None:
        """Mark a task complete and, if it recurs, immediately register the next occurrence.

        For daily/weekly tasks the completed instance is left in the dict (for history)
        and a brand-new Task is inserted so the scheduler picks it up next run.

        Returns the newly created next-occurrence Task, or None for one-time tasks.
        """
        if task_id not in self.tasks:
            raise ValueError(f"No task with id '{task_id}' found for {self.name}")

        task = self.tasks[task_id]
        task.mark_complete()
        logger.info("Completed task '%s' for %s (frequency=%s)", task.title, self.name, task.frequency)

        next_task = task.next_occurrence()
        if next_task is not None:
            self.tasks[next_task.task_id] = next_task
            logger.info("Created next occurrence of '%s' for %s", task.title, self.name)

        return next_task


@dataclass
class Schedule:
    pet: Pet
    date: str  # e.g. "2026-03-27"
    plan: list[PlanEntry] = field(default_factory=list)
    skipped: list[Task] = field(default_factory=list)

    def generate(self) -> None:
        """Build a time-ordered daily plan for this pet using a greedy single-pass algorithm.

        Steps:
        1. Filter out already-completed tasks.
        2. Sort remaining tasks by a three-key tuple: priority (high first),
           whether time_of_day is "any" (constrained windows go first),
           then by window start hour (morning before afternoon, etc.).
        3. Walk through the sorted list with a moving clock starting at the
           owner's wake_time. For each task:
           - Skip it (don't stop) if it would exceed the remaining time budget.
           - Advance the clock to the task's preferred window start if the clock
             hasn't reached it yet.
           - Record a PlanEntry with the current time and a reason string noting
             whether the task landed inside or outside its preferred window.
           - Advance the clock by task duration plus the owner's buffer.
        4. Any tasks that did not fit are stored in self.skipped.

        Results are stored in self.plan and self.skipped; call explain() to print them.
        """
        logger.info("Generating schedule for %s on %s", self.pet.name, self.date)
        pending = [t for t in self.pet.tasks.values() if not t.completed]

        # Sort key: priority (high first), then time-constrained tasks before "any",
        # then by window start hour so morning beats afternoon within the same priority group.
        sorted_tasks = sorted(
            pending,
            key=lambda t: (
                PRIORITY_ORDER[t.priority],
                t.time_of_day == "any",
                TIME_RANGES[t.time_of_day][0],
            ),
        )

        available_minutes = self.pet.owner.available_hours * 60
        buffer = self.pet.owner.task_buffer_minutes
        used_minutes = 0
        self.skipped = []

        # Use wake_time as the base for the day's clock
        current = datetime.strptime(self.pet.owner.wake_time, "%I:%M %p")

        self.plan = []

        for task in sorted_tasks:
            # Continue (don't stop) so a shorter task later may still fit
            if used_minutes + task.duration_minutes > available_minutes:
                self.skipped.append(task)
                continue

            # Get the preferred time window for this task
            range_start_h, range_end_h = TIME_RANGES[task.time_of_day]
            window_start = current.replace(hour=range_start_h, minute=0, second=0)
            window_end   = current.replace(hour=range_end_h,   minute=0, second=0)

            # Jump forward to the window if we haven't reached it yet
            if current < window_start:
                current = window_start

            # Determine whether we are inside or outside the preferred window
            out_of_window = current >= window_end and task.time_of_day != "any"
            if out_of_window:
                reason = (
                    f"{task.priority.capitalize()} priority; "
                    f"preferred {task.time_of_day} but scheduled late due to earlier tasks"
                )
            else:
                reason = (
                    f"{task.priority.capitalize()} priority; "
                    f"fits {task.time_of_day} window and within "
                    f"{self.pet.owner.available_hours}h available"
                )

            # removeprefix("0") strips only a single leading zero, so "08:30 AM" → "8:30 AM"
            # but "10:30 AM" stays intact (unlike lstrip which strips all matching chars).
            start_time_str = current.strftime("%I:%M %p").removeprefix("0")
            self.plan.append(PlanEntry(task=task, start_time=start_time_str, reason=reason))

            # Advance clock by task duration + per-owner buffer; both count against the budget.
            current += timedelta(minutes=task.duration_minutes + buffer)
            used_minutes += task.duration_minutes + buffer

        logger.info(
            "Schedule complete for %s: %d task(s) scheduled, %d skipped",
            self.pet.name, len(self.plan), len(self.skipped),
        )

    def sort_by_time(self) -> list[PlanEntry]:
        """Return the plan entries sorted chronologically by their scheduled start_time.

        Uses a lambda with datetime.strptime as the key so "8:00 AM" < "10:30 AM" < "5:00 PM"
        are compared as actual times rather than strings (which would sort lexicographically).
        """
        return sorted(
            self.plan,
            key=lambda entry: datetime.strptime(entry.start_time, "%I:%M %p"),
        )

    def conflicts(self) -> list[str]:
        """Check for overlapping tasks within this single pet's schedule.

        Strategy: pairwise O(n²) interval overlap test.
        Two tasks A and B conflict when A starts before B ends AND B starts before A ends.
        Returns warning strings so callers are informed without the program crashing.
        """
        warnings = []
        for i in range(len(self.plan)):
            for j in range(i + 1, len(self.plan)):
                a, b = self.plan[i], self.plan[j]
                a_start = datetime.strptime(a.start_time, "%I:%M %p")
                a_end   = a_start + timedelta(minutes=a.task.duration_minutes)
                b_start = datetime.strptime(b.start_time, "%I:%M %p")
                b_end   = b_start + timedelta(minutes=b.task.duration_minutes)
                if a_start < b_end and b_start < a_end:
                    a_end_str = a_end.strftime("%I:%M %p").removeprefix("0")
                    b_end_str = b_end.strftime("%I:%M %p").removeprefix("0")
                    warnings.append(
                        f"WARNING [{self.pet.name}]: '{a.task.title}' "
                        f"({a.start_time}–{a_end_str}) overlaps "
                        f"'{b.task.title}' ({b.start_time}–{b_end_str})"
                    )
        return warnings

    def explain(self) -> str:
        """Return a human-readable summary of the generated plan."""
        if not self.plan and not self.skipped:
            return "No plan yet — call generate() first."

        lines = [f"Schedule for {self.pet.name} on {self.date}:"]
        for entry in self.plan:
            lines.append(
                f"  {entry.start_time} — {entry.task.title} "
                f"({entry.task.duration_minutes} min) [{entry.task.priority}]: "
                f"{entry.reason}"
            )

        total = sum(e.task.duration_minutes for e in self.plan)
        budget = int(self.pet.owner.available_hours * 60)
        lines.append(f"\nTotal: {total} min used / {budget} min available")

        if self.skipped:
            lines.append("Could not schedule: " + ", ".join(t.title for t in self.skipped))

        return "\n".join(lines)


def detect_conflicts(schedules: list[Schedule]) -> list[str]:
    """Return all scheduling conflicts within and across a list of schedules.

    Two kinds of conflict are reported:
    - Within-pet: two tasks for the same pet overlap (shouldn't happen with the
      sequential scheduler, but guards against manual plan edits or future changes).
    - Cross-pet: tasks from different pets overlap, meaning the owner would need
      to attend to two animals at the same time.

    Returns a flat list of warning strings. An empty list means no conflicts.
    No exceptions are raised — callers decide how to present the warnings.
    """
    warnings: list[str] = []
    logger.info("Running conflict detection across %d schedule(s)", len(schedules))

    # Within each individual schedule
    for sched in schedules:
        warnings.extend(sched.conflicts())

    # Across every pair of schedules (owner can only be in one place at a time)
    for i in range(len(schedules)):
        for j in range(i + 1, len(schedules)):
            sched_a, sched_b = schedules[i], schedules[j]
            for a in sched_a.plan:
                for b in sched_b.plan:
                    a_start = datetime.strptime(a.start_time, "%I:%M %p")
                    a_end   = a_start + timedelta(minutes=a.task.duration_minutes)
                    b_start = datetime.strptime(b.start_time, "%I:%M %p")
                    b_end   = b_start + timedelta(minutes=b.task.duration_minutes)
                    if a_start < b_end and b_start < a_end:
                        a_end_str = a_end.strftime("%I:%M %p").removeprefix("0")
                        b_end_str = b_end.strftime("%I:%M %p").removeprefix("0")
                        warnings.append(
                            f"WARNING [cross-pet]: {sched_a.pet.name}'s '{a.task.title}' "
                            f"({a.start_time}–{a_end_str}) overlaps "
                            f"{sched_b.pet.name}'s '{b.task.title}' ({b.start_time}–{b_end_str})"
                        )

    if warnings:
        for w in warnings:
            logger.warning("%s", w)
    else:
        logger.info("No conflicts found")
    return warnings
