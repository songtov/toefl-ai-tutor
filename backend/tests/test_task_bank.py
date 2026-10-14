from collections import Counter

from app.domain.task import SET_LAYOUT, TaskType
from app.infrastructure.task_bank import load_bank, load_sets


def test_bank_has_every_task_type():
    counts = Counter(t.type for t in load_bank().values())
    assert counts == {
        TaskType.BUILD_SENTENCE: 100,
        TaskType.EMAIL: 12,
        TaskType.ACADEMIC_DISCUSSION: 10,
    }


def test_sets_follow_the_writing_section_layout():
    bank = load_bank()
    sets = load_sets()
    assert len(sets) == 5
    for s in sets.values():
        assert tuple(bank[i].type for i in s.task_ids) == SET_LAYOUT
