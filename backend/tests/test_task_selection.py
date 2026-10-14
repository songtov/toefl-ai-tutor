from app.application.task_selection import pick_email_tasks
from app.infrastructure.task_bank import load_email_tasks


def test_bank_loads_with_unique_ids():
    bank = load_email_tasks()
    assert len(bank) == 10
    assert len({t.id for t in bank}) == len(bank)


def test_picks_unseen_tasks_first():
    bank = load_email_tasks()
    seen = {t.id for t in bank[:8]}
    picked = pick_email_tasks(bank, seen, k=3)
    assert len({t.id for t in picked}) == 3
    assert {t.id for t in bank[8:]} <= {t.id for t in picked}
