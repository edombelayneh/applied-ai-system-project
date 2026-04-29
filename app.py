import json
import logging

import streamlit as st
from groq import Groq
from pawpal_system import Owner, Pet, Task, Schedule, TIME_RANGES, PRIORITY_ORDER

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("pawpal.log"),
    ],
)
app_logger = logging.getLogger("pawpal.app")

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

st.divider()

# --- Owner ---
st.subheader("Owner")
col1, col2, col3, col4 = st.columns(4)
with col1:
    owner_name = st.text_input("Owner name", value="Jordan")
with col2:
    available_hours = st.number_input("Available hours today", min_value=0.5, max_value=16.0, value=3.0, step=0.5)
with col3:
    wake_time = st.text_input("Wake time", value="7:00 AM")
with col4:
    buffer_minutes = st.number_input("Buffer between tasks (min)", min_value=0, max_value=30, value=5, step=1)

if (
    "owner" not in st.session_state
    or st.session_state.owner.name != owner_name
    or st.session_state.owner.available_hours != available_hours
    or st.session_state.owner.wake_time != wake_time
    or st.session_state.owner.task_buffer_minutes != int(buffer_minutes)
):
    try:
        st.session_state.owner = Owner(
            name=owner_name,
            available_hours=available_hours,
            wake_time=wake_time,
            task_buffer_minutes=int(buffer_minutes),
        )
    except ValueError as e:
        st.error(str(e))

st.divider()

# --- Add a Pet ---
st.subheader("Add a Pet")
col1, col2 = st.columns(2)
with col1:
    pet_name = st.text_input("Pet name", value="Mochi")
with col2:
    species = st.selectbox("Species", ["dog", "cat", "other"])

if st.button("Add pet"):
    new_pet = Pet(name=pet_name, species=species, owner=st.session_state.owner)
    st.session_state.owner.pets.append(new_pet)
    st.success(f"Added {pet_name} the {species}!")

if st.session_state.owner.pets:
    st.write("Pets:", ", ".join(f"{p.name} ({p.species})" for p in st.session_state.owner.pets))
else:
    st.info("No pets yet. Add one above.")

st.divider()

# --- AI Task Suggestions ---
st.subheader("AI Task Suggestions")

if not st.session_state.owner.pets:
    st.info("Add a pet above to get AI-suggested tasks.")
else:
    suggest_pet_name = st.selectbox(
        "Suggest tasks for",
        [p.name for p in st.session_state.owner.pets],
        key="suggest_pet_select",
    )
    suggest_pet = next(p for p in st.session_state.owner.pets if p.name == suggest_pet_name)

    if st.button("Suggest tasks with AI", key="suggest_btn"):
        with st.spinner(f"Asking AI for {suggest_pet.name} task ideas..."):
            prompt = (
                f"Suggest 5 daily care tasks for a {suggest_pet.species} named {suggest_pet.name}.\n\n"
                f"Return ONLY a valid JSON array with no extra text or markdown fences. "
                f"Each object must have exactly these fields: "
                f'"title" (string), "duration_minutes" (integer 5–60), '
                f'"priority" ("low"/"medium"/"high"), '
                f'"time_of_day" ("morning"/"afternoon"/"evening"/"any"), '
                f'"frequency" ("once"/"daily"/"weekly").\n\n'
                f'Example: [{{"title":"Morning walk","duration_minutes":30,'
                f'"priority":"high","time_of_day":"morning","frequency":"daily"}}]'
            )
            try:
                client = Groq()
                app_logger.info(
                    "Requesting AI task suggestions for %s (%s)",
                    suggest_pet.name, suggest_pet.species,
                )
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    stream=False,
                )
                raw = response.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                suggestions = json.loads(raw)
                st.session_state.ai_suggestions = suggestions
                st.session_state.ai_suggestions_pet = suggest_pet_name
                app_logger.info(
                    "Received %d suggestions for %s", len(suggestions), suggest_pet.name
                )
            except json.JSONDecodeError:
                st.error("AI returned an unexpected format — please try again.")
                app_logger.warning(
                    "Failed to parse AI suggestions JSON for %s", suggest_pet.name
                )
            except Exception as e:
                if "auth" in str(e).lower() or "api key" in str(e).lower() or "401" in str(e):
                    st.error("GROQ_API_KEY is missing or invalid. Get a free key at console.groq.com.")
                else:
                    st.error(f"Error calling Groq: {e}")
                app_logger.error("Groq error during suggestions: %s", e)

    if (
        "ai_suggestions" in st.session_state
        and st.session_state.get("ai_suggestions_pet") == suggest_pet_name
        and st.session_state.ai_suggestions
    ):
        st.markdown(f"**Suggested tasks for {suggest_pet_name}** — click Add to include:")
        for i, s in enumerate(st.session_state.ai_suggestions):
            cols = st.columns([3, 1, 1, 1, 1, 1])
            cols[0].write(s.get("title", ""))
            cols[1].write(f"{s.get('duration_minutes', '?')} min")
            cols[2].write(s.get("priority", ""))
            cols[3].write(s.get("time_of_day", ""))
            cols[4].write(s.get("frequency", ""))
            if cols[5].button("Add", key=f"add_suggestion_{i}"):
                try:
                    task = Task(
                        title=s["title"],
                        duration_minutes=int(s["duration_minutes"]),
                        priority=s["priority"],
                        time_of_day=s["time_of_day"],
                        frequency=s.get("frequency", "once"),
                    )
                    suggest_pet.add_task(task)
                    st.success(f"Added '{s['title']}' to {suggest_pet_name}.")
                    app_logger.info(
                        "Added AI-suggested task '%s' to %s", s["title"], suggest_pet_name
                    )
                except (ValueError, KeyError) as e:
                    st.error(f"Could not add task: {e}")

st.divider()

# --- Add a Task ---
st.subheader("Schedule a Task")

if not st.session_state.owner.pets:
    st.warning("Add a pet first.")
else:
    pet_names = [p.name for p in st.session_state.owner.pets]
    selected_pet_name = st.selectbox("Select pet", pet_names)
    selected_pet = next(p for p in st.session_state.owner.pets if p.name == selected_pet_name)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        task_title = st.text_input("Task title", value="Morning walk")
    with col2:
        duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
    with col3:
        priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
    with col4:
        time_of_day = st.selectbox("Time of day", ["morning", "afternoon", "evening", "any"])

    if st.button("Add task"):
        task = Task(title=task_title, duration_minutes=int(duration), priority=priority, time_of_day=time_of_day)
        selected_pet.add_task(task)
        st.success(f"Added '{task_title}' to {selected_pet_name}.")

    if selected_pet.tasks:
        st.write(f"{selected_pet_name}'s tasks:")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.selectbox(
                "Filter by status", ["all", "pending", "completed"], key="task_status_filter"
            )
        with col_f2:
            sort_order = st.selectbox(
                "Sort by", ["default", "time of day", "priority", "duration"], key="task_sort"
            )

        tasks_to_show = list(selected_pet.tasks.values())

        if status_filter == "pending":
            tasks_to_show = [t for t in tasks_to_show if not t.completed]
        elif status_filter == "completed":
            tasks_to_show = [t for t in tasks_to_show if t.completed]

        if sort_order == "time of day":
            tasks_to_show = sorted(tasks_to_show, key=lambda t: TIME_RANGES[t.time_of_day][0])
        elif sort_order == "priority":
            tasks_to_show = sorted(tasks_to_show, key=lambda t: PRIORITY_ORDER[t.priority])
        elif sort_order == "duration":
            tasks_to_show = sorted(tasks_to_show, key=lambda t: t.duration_minutes)

        st.table([
            {
                "title": t.title,
                "duration (min)": t.duration_minutes,
                "priority": t.priority,
                "time of day": t.time_of_day,
                "status": "done" if t.completed else "pending",
            }
            for t in tasks_to_show
        ])
    else:
        st.info(f"No tasks yet for {selected_pet_name}.")

st.divider()

# --- Task Overview (all pets) ---
st.subheader("Task Overview")

if not st.session_state.owner.pets:
    st.info("No pets yet.")
else:
    all_pets = st.session_state.owner.pets
    pet_filter_options = ["All pets"] + [p.name for p in all_pets]

    col_p, col_s, col_so = st.columns(3)
    with col_p:
        pet_filter = st.selectbox("Filter by pet", pet_filter_options, key="overview_pet")
    with col_s:
        overview_status = st.selectbox(
            "Filter by status", ["all", "pending", "completed"], key="overview_status"
        )
    with col_so:
        overview_sort = st.selectbox(
            "Sort by", ["default", "time of day", "priority", "duration"], key="overview_sort"
        )

    if pet_filter == "All pets":
        all_tasks = [
            (p.name, t)
            for p in all_pets
            for t in p.tasks.values()
        ]
    else:
        target_pet = next(p for p in all_pets if p.name == pet_filter)
        all_tasks = [(target_pet.name, t) for t in target_pet.tasks.values()]

    if overview_status == "pending":
        all_tasks = [(pn, t) for pn, t in all_tasks if not t.completed]
    elif overview_status == "completed":
        all_tasks = [(pn, t) for pn, t in all_tasks if t.completed]

    if overview_sort == "time of day":
        all_tasks = sorted(all_tasks, key=lambda x: TIME_RANGES[x[1].time_of_day][0])
    elif overview_sort == "priority":
        all_tasks = sorted(all_tasks, key=lambda x: PRIORITY_ORDER[x[1].priority])
    elif overview_sort == "duration":
        all_tasks = sorted(all_tasks, key=lambda x: x[1].duration_minutes)

    if all_tasks:
        st.table([
            {
                "pet": pn,
                "title": t.title,
                "duration (min)": t.duration_minutes,
                "priority": t.priority,
                "time of day": t.time_of_day,
                "status": "done" if t.completed else "pending",
            }
            for pn, t in all_tasks
        ])
    else:
        st.info("No tasks match the selected filters.")

st.divider()

# --- Generate Schedule ---
st.subheader("Build Schedule")

if not st.session_state.owner.pets:
    st.warning("Add a pet and some tasks first.")
else:
    sched_pet_name = st.selectbox("Schedule for", [p.name for p in st.session_state.owner.pets], key="sched_select")
    sched_pet = next(p for p in st.session_state.owner.pets if p.name == sched_pet_name)

    if st.button("Generate schedule"):
        from datetime import date
        from pawpal_system import detect_conflicts

        schedule = Schedule(pet=sched_pet, date=str(date.today()))
        schedule.generate()
        st.session_state.last_schedule = schedule
        st.session_state.last_schedule_pet_name = sched_pet_name

        # --- Conflict warnings ---
        conflicts = detect_conflicts([schedule])
        if conflicts:
            st.warning(
                f"**{len(conflicts)} scheduling conflict(s) found.** "
                "Two tasks are scheduled at the same time — adjust a duration or time window to fix this."
            )
            for msg in conflicts:
                # Strip the raw "WARNING [...]: " prefix for a friendlier label
                friendly = msg.replace("WARNING ", "").strip()
                # cross-pet conflicts use a different icon to distinguish them
                icon = "🐾" if "[cross-pet]" in msg else "⏰"
                st.warning(f"{icon} {friendly}")
        else:
            st.success("No conflicts — your schedule looks good!")

        # --- Scheduled tasks table ---
        if schedule.plan:
            st.markdown(f"**{sched_pet.name}'s plan for {date.today()}**")
            st.table([
                {
                    "Time": e.start_time,
                    "Task": e.task.title,
                    "Duration": f"{e.task.duration_minutes} min",
                    "Priority": e.task.priority.capitalize(),
                    "Window": e.task.time_of_day.capitalize(),
                    "Note": e.reason,
                }
                for e in schedule.sort_by_time()
            ])
            total = sum(e.task.duration_minutes for e in schedule.plan)
            budget = int(sched_pet.owner.available_hours * 60)
            st.caption(f"Time used: {total} min / {budget} min available")

        # --- Tasks that didn't fit ---
        if schedule.skipped:
            skipped_names = ", ".join(f"**{t.title}**" for t in schedule.skipped)
            st.warning(
                f"These tasks didn't fit in today's schedule: {skipped_names}. "
                "Try increasing available hours or removing lower-priority tasks."
            )

    # --- AI Explanation (shown after a schedule has been generated) ---
    if (
        "last_schedule" in st.session_state
        and st.session_state.get("last_schedule_pet_name") == sched_pet_name
    ):
        st.divider()
        st.subheader("AI Schedule Explanation")
        if st.button("Explain my schedule with AI", key="explain_btn"):
            _sched = st.session_state.last_schedule
            _pet = _sched.pet
            _owner = _pet.owner

            plan_lines = "\n".join(
                f"- {e.start_time}: {e.task.title} "
                f"({e.task.duration_minutes} min, {e.task.priority} priority, "
                f"{e.task.time_of_day} window)"
                for e in _sched.sort_by_time()
            )
            skipped_line = (
                ", ".join(t.title for t in _sched.skipped) if _sched.skipped else "none"
            )
            total_used = sum(e.task.duration_minutes for e in _sched.plan)
            budget_min = int(_owner.available_hours * 60)

            prompt = (
                f"You are a friendly pet care assistant. Explain this daily care schedule "
                f"for {_pet.name} the {_pet.species} in a warm, practical tone.\n\n"
                f"Owner: {_owner.name} | Wake time: {_owner.wake_time} | "
                f"Available: {_owner.available_hours}h ({budget_min} min)\n\n"
                f"Schedule for {_sched.date}:\n{plan_lines}\n\n"
                f"Time used: {total_used} min / {budget_min} min\n"
                f"Tasks that didn't fit: {skipped_line}\n\n"
                f"In 2-3 short paragraphs: explain what the day looks like, why tasks are "
                f"ordered this way (priority + time windows), and give one practical tip. "
                f"If tasks were skipped, briefly explain why and suggest a fix."
            )

            placeholder = st.empty()
            full_text = ""
            try:
                app_logger.info(
                    "Requesting AI explanation for %s's schedule (%d tasks)",
                    _pet.name, len(_sched.plan),
                )
                client = Groq()
                stream = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    stream=True,
                )
                for chunk in stream:
                    text = chunk.choices[0].delta.content or ""
                    full_text += text
                    placeholder.markdown(full_text + "▌")
                placeholder.markdown(full_text)
                app_logger.info("AI explanation complete for %s", _pet.name)
            except Exception as e:
                if "auth" in str(e).lower() or "api key" in str(e).lower() or "401" in str(e):
                    st.error(
                        "GROQ_API_KEY is missing or invalid. "
                        "Get a free key at groq.com, then run: export GROQ_API_KEY=your_key"
                    )
                else:
                    st.error(f"Error calling Groq: {e}")
