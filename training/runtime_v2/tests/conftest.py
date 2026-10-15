import copy
import pytest


@pytest.fixture
def record():
    # Artificial fixture, unrelated to private TRAIN/DEV/TEST.
    case = {"schema_version": "runtime-1.0", "category": "MODEL_NEGOTIATOR", "difficulty": "medium",
        "scenario": "negotiation_only", "conflict_type": "none",
        "public": {"title": "Искусственная сцена", "context": "Два вымышленных участника обсуждают коробку.",
            "student_role": "Покупатель", "negotiation_topic": "Обсудить передачу коробки",
            "player_conflict_goal": None, "known_facts": ["Коробка синяя"], "participants": []},
        "world": {"facts": ["Коробка синяя"], "unknowns": ["Место передачи неизвестно"]},
        "opponent": {"name": "Тестовый персонаж", "role": "Продавец", "opening": "Где вам удобно встретиться?",
            "private_facts": ["Предпочитает утро"], "goals": ["Договориться о месте"],
            "hard_limits": ["Не встречается ночью"], "concede_if": ["Предложено дневное время"],
            "escalate_if": [], "initial_emotion": "Спокоен"},
        "teaching": {"perspective": "not_applicable", "conflict_type": "none",
            "negotiation_topic": "Обсудить передачу коробки", "conflict_goal": None, "decoding": None,
            "initial_stage": "negotiation", "focus_techniques": ["SECRET_CANARY_TECHNIQUE"],
            "acceptable_outcomes": ["SECRET_CANARY_ORACLE"]}}
    return {"dataset_version": "runtime-train-v2.0", "case_id": "SYNTHETIC001", "branch_id": "test",
            "language": "ru", "runtime_case": case,
            "dialogue": [{"speaker": "opponent", "text": case["opponent"]["opening"]},
                         {"speaker": "player", "text": "Встретимся завтра днём?"},
                         {"speaker": "opponent", "text": "Да. Где именно?"},
                         {"speaker": "player", "text": "У входа."},
                         {"speaker": "opponent", "text": "Хорошо, у входа."}]}
