import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from itertools import combinations


# -----------------------------
# Structures de données
# -----------------------------

@dataclass
class Person:
    name: str
    available: Set[str]
    likes_people: Set[str]
    dislikes_people: Set[str]
    preferred_tasks: Set[str]
    disliked_tasks: Set[str]
    home_location: str

    @staticmethod
    def from_dict(d: Dict):
        return Person(
            name=d["name"],
            available=set(d.get("available", [])),
            likes_people=set(d.get("likes_people", [])),
            dislikes_people=set(d.get("dislikes_people", [])),
            preferred_tasks=set(d.get("preferred_tasks", [])),
            disliked_tasks=set(d.get("disliked_tasks", [])),
            home_location=d.get("home_location", ""),
        )


@dataclass
class Task:
    name: str
    required_people: List[str]
    min_people: int
    max_people: int
    preferred_people: List[str]
    forbidden_people: List[str]
    preferred_locations: List[str]
    allowed_locations: List[str]
    preferred_timeslots: List[str]
    value: int

    @staticmethod
    def from_dict(d: Dict):
        return Task(
            name=d["name"],
            required_people=d.get("required_people", []),
            min_people=d.get("min_people", 0),
            max_people=d.get("max_people", 0),
            preferred_people=d.get("preferred_people", []),
            forbidden_people=d.get("forbidden_people", []),
            preferred_locations=d.get("preferred_locations", []),
            allowed_locations=d.get("allowed_locations", []),
            preferred_timeslots=d.get("preferred_timeslots", []),
            value=d.get("value", 0),
        )


@dataclass
class Assignment:
    task_name: str
    timeslot: str
    location: str
    people: List[str]
    score: int


# -----------------------------
# Lecture JSON
# -----------------------------


def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------
# Planification
# -----------------------------


def score_task_assignment(
    task: Task,
    people: List[str],
    timeslot: str,
    location: str,
    people_by_name: Dict[str, Person],
) -> int:
    score = task.value

    required = set(task.required_people)
    if not required.issubset(people):
        return -10_000

    if any(p in task.forbidden_people for p in people):
        return -10_000

    for p in people:
        person = people_by_name.get(p)
        if person is None:
            continue

        if p in task.preferred_people:
            score += 2

        if p in person.likes_people:
            score += 1

        if p in person.dislikes_people:
            score -= 2

        if task.name in person.preferred_tasks:
            score += 2

        if task.name in person.disliked_tasks:
            score -= 3

    if location in task.preferred_locations:
        score += 2
    if location not in task.allowed_locations:
        score -= 20

    if timeslot in task.preferred_timeslots:
        score += 1

    if len(people) >= task.min_people:
        score += 5

    if len(people) > task.max_people:
        score -= 100

    return score


def generate_candidates_for_task(
    task: Task,
    timeslot: str,
    people_by_name: Dict[str, Person],
    assigned_people_by_slot: Dict[str, Set[str]],
) -> List[List[str]]:
    available = []
    for person_name, person in people_by_name.items():
        if timeslot in person.available and person_name not in assigned_people_by_slot.get(timeslot, set()):
            available.append(person_name)

    available = [p for p in available if p not in task.forbidden_people]

    required = task.required_people
    # priorité aux required_people
    def rank(person_name: str) -> int:
        person = people_by_name[person_name]
        r = 0
        if person_name in task.preferred_people:
            r += 10
        if task.name in person.preferred_tasks:
            r += 5
        if person_name in person.likes_people:
            r += 2
        if person_name in person.dislikes_people:
            r -= 2
        if task.name in person.disliked_tasks:
            r -= 4
        return r

    ordered = sorted(available, key=rank, reverse=True)
    results: List[List[str]] = []

    for size in range(task.min_people, min(task.max_people, len(ordered)) + 1):
        combo = ordered[:size]
        if set(required).issubset(combo):
            results.append(combo)

    if not results:
        req_combo = [r for r in required if r in available]
        if len(req_combo) == len(required):
            results.append(req_combo)

    return results


def solve_task_schedule(task_json_path: str) -> List[Assignment]:
    data = load_json(task_json_path)
    tasks = [Task.from_dict(t) for t in data["tasks"]]
    people = {p["name"]: Person.from_dict(p) for p in data["characters"]}
    timeslots = data["timeslots"]
    locations = data["locations"]

    tasks = sorted(
        tasks,
        key=lambda t: (
            -len(t.required_people),
            -t.value,
            -len(t.preferred_people),
            -t.min_people,
        ),
    )

    assigned_people_by_slot: Dict[str, Set[str]] = {ts: set() for ts in timeslots}
    schedule: List[Assignment] = []

    for task in tasks:
        best_assignment: Optional[Assignment] = None
        best_score = -10**9

        for ts in timeslots:
            for loc in locations:
                candidates = generate_candidates_for_task(task, ts, people, assigned_people_by_slot)
                for people_list in candidates:
                    if any(p in assigned_people_by_slot[ts] for p in people_list):
                        continue

                    score = score_task_assignment(task, people_list, ts, loc, people)
                    if score > best_score:
                        best_score = score
                        best_assignment = Assignment(
                            task_name=task.name,
                            timeslot=ts,
                            location=loc,
                            people=people_list,
                            score=score,
                        )

        if best_assignment is not None:
            schedule.append(best_assignment)
            for p in best_assignment.people:
                assigned_people_by_slot[best_assignment.timeslot].add(p)

    return schedule


# -----------------------------
# Seating arrangement
# -----------------------------


def score_seating_group(group: List[str], likes_map: Dict[str, Set[str]], dislikes_map: Dict[str, Set[str]]) -> int:
    score = 0
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            a, b = group[i], group[j]
            if b in likes_map.get(a, set()):
                score += 5
            if b in dislikes_map.get(a, set()):
                score -= 7
    return score


def solve_seating(seating_json_path: str) -> List[str]:
    data = load_json(seating_json_path)
    people = data["people"]
    names = [p["name"] for p in people]

    likes_map = {}
    dislikes_map = {}
    for p in people:
        name = p["name"]
        likes_map[name] = set(p.get("likes", {}).get("people", []))
        dislikes_map[name] = set(p.get("dislikes", {}).get("people", []))

    best_group = []
    best_score = -10**9

    for size in range(2, min(6, len(names)) + 1):
        for combo in combinations(names, size):
            s = score_seating_group(list(combo), likes_map, dislikes_map)
            if s > best_score:
                best_score = s
                best_group = list(combo)

    return best_group


# -----------------------------
# Main
# -----------------------------

if __name__ == "__main__":
    print("=== Grey + GaussBlur, GPU - project implementation ===")

    schedule = solve_task_schedule("task_scheduling.json")
    if schedule:
        total = sum(a.score for a in schedule)
        print("\nPlanification trouvée :")
        for a in schedule:
            print(f"- {a.task_name} | {a.timeslot} | {a.location} | score={a.score} | {', '.join(a.people)}")
        print(f"\nScore total : {total}")
    else:
        print("Aucune planification valide trouvée.")

    best_group = solve_seating("seating_arrangement.json")
    print("\nMeilleur groupe de seating :")
    print(best_group)
