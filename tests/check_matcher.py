"""Ad-hoc checks for the matcher. Run: .venv/bin/python -m tests.check_matcher"""
import random
import sys

sys.path.insert(0, ".")
from app.matcher import draw_names
from app.models import Participant, new_id


def people(n, with_exclusions=False):
    ps = [Participant(id=new_id(), name=f"P{i}", email=f"p{i}@x.com") for i in range(n)]
    if with_exclusions:
        rng = random.Random(42)
        for p in ps:
            others = [q.id for q in ps if q.id != p.id]
            if len(others) > 2:
                p.exclusions = rng.sample(others, 2)
    return ps


def check_assignment(ps, assignment, no_reciprocal=False):
    by_id = {p.id: p for p in ps}
    assert len(assignment) == len(ps), "every giver must have exactly one recipient"
    recipients = list(assignment.values())
    assert len(set(recipients)) == len(recipients), "recipients must be distinct"
    for giver, rec in assignment.items():
        p = by_id[giver]
        assert rec != giver, f"{p.name} drew themselves"
        assert rec not in p.exclusions, f"{p.name} drew an excluded person"
        if no_reciprocal:
            assert assignment.get(rec) != giver, f"reciprocal pair {giver}<->{rec}"


# 1. basic: 2 people
ps = people(2)
a = draw_names(ps)
check_assignment(ps, a)
assert len(a) == 2

# 2. many people, repeated draws
for trial in range(200):
    ps = people(12)
    check_assignment(ps, draw_names(ps))

# 3. with exclusions
for trial in range(200):
    ps = people(20, with_exclusions=True)
    check_assignment(ps, draw_names(ps))

# 4. no_reciprocal
for trial in range(200):
    ps = people(15, with_exclusions=True)
    check_assignment(ps, draw_names(ps, no_reciprocal=True), no_reciprocal=True)

# 5. impossible even though everyone has a candidate:
#    A->{B}, B->{A}, C->{A}, D->{B}  =>  A<->B forced, C and D starve.
A, B, C, D = people(4)
A.exclusions = [C.id, D.id]   # A must draw B
B.exclusions = [C.id, D.id]   # B must draw A
C.exclusions = [B.id, D.id]   # C must draw A (already taken) -> no solution
D.exclusions = [A.id, C.id]   # D must draw B (already taken)
try:
    draw_names([A, B, C, D])
    raise AssertionError("should have raised")
except ValueError as e:
    assert "No valid assignment" in str(e)

# 6. impossible: someone excludes everyone
ps = people(3)
ps[0].exclusions = [q.id for q in ps if q.id != ps[0].id]
try:
    draw_names(ps)
    raise AssertionError("should have raised")
except ValueError as e:
    assert "can't draw anyone" in str(e)

# 7. too few people
try:
    draw_names(people(1))
    raise AssertionError("should have raised")
except ValueError:
    pass

# 8. determinism with seeded rng
ps = people(10)
a1 = draw_names(ps, rng=random.Random(7))
a2 = draw_names(ps, rng=random.Random(7))
assert a1 == a2

print("all matcher checks passed")
