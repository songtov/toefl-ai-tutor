from app.infrastructure.task_bank import load_email_sets, load_email_tasks


def test_every_bank_task_is_in_exactly_one_set():
    tasks = load_email_tasks()
    sets = load_email_sets()
    assert len(tasks) == 12
    assert all(len(s.task_ids) == 3 for s in sets.values())
    assert sorted(i for s in sets.values() for i in s.task_ids) == sorted(tasks)
