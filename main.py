import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from itertools import combinations


# ---------------------------------------------------------------------------
# Ce fichier contient le moteur principal du projet.
# Il lit les fichiers JSON, modélise les données, applique les contraintes,
# calcule un score, puis cherche une solution satisfaisante.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1) Structures de données
# ---------------------------------------------------------------------------
# Une classe Person représente une personne avec ses disponibilités,
# ses préférences et ses antipathies.
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
        # Convertit un dictionnaire JSON en objet Person.
        return Person(
            name=d["name"],
            available=set(d.get("available", [])),
            likes_people=set(d.get("likes_people", [])),
            dislikes_people=set(d.get("dislikes_people", [])),
            preferred_tasks=set(d.get("preferred_tasks", [])),
            disliked_tasks=set(d.get("disliked_tasks", [])),
            home_location=d.get("home_location", ""),
        )


# Une classe Task représente une tâche du planning avec ses contraintes.
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
        # Convertit un dictionnaire JSON en objet Task.
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


# Une affectation représente une tâche planifiée avec son créneau,
# son lieu, les personnes qui la font et son score.
@dataclass
class Assignment:
    task_name: str
    timeslot: str
    location: str
    people: List[str]
    score: int


# ---------------------------------------------------------------------------
# 2) Lecture des fichiers JSON
# ---------------------------------------------------------------------------
# Cette fonction charge un fichier JSON et le transforme en diction Python.
def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 3) Planification des tâches
# ---------------------------------------------------------------------------
# Cette partie décide quelles personnes doivent participer à chaque tâche,
# à quel moment et dans quel lieu, en tenant compte des contraintes.

def score_task_assignment(
    task: Task,
    people: List[str],
    timeslot: str,
    location: str,
    people_by_name: Dict[str, Person],
) -> int:
    # On initialise le score avec la valeur de base de la tâche.
    score = task.value

    # Si les personnes obligatoires ne sont pas toutes présentes,
    # alors la tâche est invalide et reçoit un très fort malus.
    required = set(task.required_people)
    if not required.issubset(people):
        return -10_000

    # Si une personne interdite est présente, la tâche est rejetée.
    if any(p in task.forbidden_people for p in people):
        return -10_000

    # On calcule le score selon les préférences et les antipathies.
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

    # Bonus si la tâche est dans un endroit privilégié.
    if location in task.preferred_locations:
        score += 2
    if location not in task.allowed_locations:
        score -= 20

    # Bonus si la tâche est dans un créneau privilégié.
    if timeslot in task.preferred_timeslots:
        score += 1

    # On favorise les tâches qui ont un nombre de participants satisfaisant.
    if len(people) >= task.min_people:
        score += 5

    # Si on dépasse le nombre maximum de personnes autorisées,
    # on applique une pénalité sévère.
    if len(people) > task.max_people:
        score -= 100

    return score


def generate_candidates_for_task(
    task: Task,
    timeslot: str,
    people_by_name: Dict[str, Person],
    assigned_people_by_slot: Dict[str, Set[str]],
) -> List[List[str]]:
    # On récupère toutes les personnes disponibles à ce créneau,
    # en excluant celles déjà attribuées au même créneau.
    available = []
    for person_name, person in people_by_name.items():
        if timeslot in person.available and person_name not in assigned_people_by_slot.get(timeslot, set()):
            available.append(person_name)

    # Les personnes interdites ne peuvent jamais être choisies.
    available = [p for p in available if p not in task.forbidden_people]

    # Fonction de classement des candidats selon leur compatibilité.
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

    # On trie les personnes de la plus compatible à la moins compatible.
    ordered = sorted(available, key=rank, reverse=True)
    results: List[List[str]] = []

    # On teste plusieurs tailles de groupe entre le minimum et le maximum.
    for size in range(task.min_people, min(task.max_people, len(ordered)) + 1):
        combo = ordered[:size]
        if set(task.required_people).issubset(combo):
            results.append(combo)

    # Si aucune combinaison n'a été trouvée avec un groupe normal,
    # on tente au moins de garder les personnes obligatoires.
    if not results:
        req_combo = [r for r in task.required_people if r in available]
        if len(req_combo) == len(task.required_people):
            results.append(req_combo)

    return results


def solve_task_schedule(task_json_path: str) -> List[Assignment]:
    # On charge les données du fichier JSON de planification.
    data = load_json(task_json_path)

    # On transforme les tâches et les personnages en objets Python plus faciles à exploiter.
    tasks = [Task.from_dict(t) for t in data["tasks"]]
    people = {p["name"]: Person.from_dict(p) for p in data["characters"]}
    timeslots = data["timeslots"]
    locations = data["locations"]

    # On trie les tâches pour traiter d'abord les plus compliquées.
    tasks = sorted(
        tasks,
        key=lambda t: (
            -len(t.required_people),
            -t.value,
            -len(t.preferred_people),
            -t.min_people,
        ),
    )

    # Ce dictionnaire mémorise les personnes déjà affectées à chaque créneau.
    assigned_people_by_slot: Dict[str, Set[str]] = {ts: set() for ts in timeslots}
    schedule: List[Assignment] = []

    # Pour chaque tâche, on cherche la meilleure affectation possible.
    for task in tasks:
        best_assignment: Optional[Assignment] = None
        best_score = -10**9

        for ts in timeslots:
            for loc in locations:
                candidates = generate_candidates_for_task(task, ts, people, assigned_people_by_slot)
                for people_list in candidates:
                    # Si un membre de cette combinaison est déjà pris à ce créneau,
                    # on évite cette solution pour ne pas avoir de conflit.
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

        # Si une bonne affectation a été trouvée, on la garde.
        if best_assignment is not None:
            schedule.append(best_assignment)
            for p in best_assignment.people:
                assigned_people_by_slot[best_assignment.timeslot].add(p)

    return schedule


# ---------------------------------------------------------------------------
# 4) Arrangement des personnes / seating
# ---------------------------------------------------------------------------
# Cette partie cherche un groupe de personnes qui se complètent le mieux
# en fonction des likes et dislikes.

def score_seating_group(group: List[str], likes_map: Dict[str, Set[str]], dislikes_map: Dict[str, Set[str]]) -> int:
    # On attribue des points si un membre aime un autre membre du groupe.
    # On retire des points si quelqu'un déteste quelqu'un d'autre dans le groupe.
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
    # On lit le fichier JSON des personnes et de leurs relations.
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

    # On teste plusieurs tailles de groupe pour trouver la meilleure composition.
    for size in range(2, min(6, len(names)) + 1):
        for combo in combinations(names, size):
            s = score_seating_group(list(combo), likes_map, dislikes_map)
            if s > best_score:
                best_score = s
                best_group = list(combo)

    return best_group


# ---------------------------------------------------------------------------
# 5) Fonction principale
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Grey + GaussBlur, GPU - projet d'implémentation ===")

    # Étape 1 : résoudre la planification de tâches.
    schedule = solve_task_schedule("task_scheduling.json")
    if schedule:
        total = sum(a.score for a in schedule)
        print("\nPlanification trouvée :")
        for a in schedule:
            print(f"- {a.task_name} | {a.timeslot} | {a.location} | score={a.score} | {', '.join(a.people)}")
        print(f"\nScore total : {total}")
    else:
        print("Aucune planification valide trouvée.")

    # Étape 2 : résoudre le groupe de seating.
    best_group = solve_seating("seating_arrangement.json")
    print("\nMeilleur groupe de seating :")
    print(best_group)
