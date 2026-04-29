# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors


## Demo

<img width="728" height="759" alt="Screenshot 2026-03-27 at 4 45 36 PM" src="https://github.com/user-attachments/assets/9fc2206a-4d5f-4e1b-accb-38a4d19a90e6" />

<img width="728" height="763" alt="Screenshot 2026-03-27 at 4 46 11 PM" src="https://github.com/user-attachments/assets/4e315fca-e200-4b20-8276-451d13127f1d" />

<img width="814" height="736" alt="Screenshot 2026-03-27 at 4 45 08 PM" src="https://github.com/user-attachments/assets/6e68cb13-e05e-4efc-8236-990a114c03ba" />



## Smarter Scheduling

The scheduler goes beyond the basic greedy planner with several new features:

- Sort order: tasks are sorted by priority first, then by time-of-day window so morning tasks always come before afternoon ones at the same priority level. Tasks marked "any" fill leftover slots last.
- Skip, don't stop: if a task does not fit the remaining time budget the scheduler skips it and keeps going, so a shorter task later in the list can still be placed.
- Adjustable buffer: each owner has a configurable gap between tasks (default 5 minutes) that counts against the daily budget and gives the owner real transition time.
- Recurring tasks: tasks can be set to repeat daily, weekly, or just once. Completing a recurring task automatically creates a fresh copy for the next run.
- Sort by time: the generated plan can be returned in strict chronological order using an actual time comparison, not alphabetical string sorting.
- Filter tasks: tasks across all pets can be filtered by pet name, completion status, or both.
- Conflict detection: the scheduler checks for overlapping tasks within one pet's plan and across different pets. It returns plain warning messages instead of crashing the program.

## Testing PawPal+

Run tests with:

```bash
python -m pytest tests/test_pawpal.py -v
```

The 23 tests cover four areas:

- Sorting correctness: tasks return in true chronological order, high priority before low, constrained windows before "any"
- Recurrence logic: completing a daily/weekly task creates a new pending copy; once tasks do not
- Conflict detection: overlapping tasks are flagged, adjacent tasks are not, cross-pet conflicts are caught
- Budget edge cases: exact-fit tasks are scheduled, oversized tasks are skipped, completed tasks are excluded

Confidence level: 4 / 5 stars. Core scheduling logic is fully tested. The UI layer, explain() output, and late wake_time edge cases are not yet covered.

---

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here   # Windows: set GROQ_API_KEY=your_key_here
```

Get a free API key (no credit card required) at [console.groq.com](https://console.groq.com).

### Run

```bash
streamlit run app.py
```

Logs are written to `pawpal.log` in the project directory.

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.
