"""Live demo difficulty tuning without changing the frozen Cloud-A serializer.

The canonical generator_prompt / roleplay_messages remain byte-for-byte stable
for training parity and golden replay tests. These additions apply only to the
interactive demo; roleplayer additions require explicit spoken style.
"""
from __future__ import annotations

from .prompts import generator_prompt
from .spoken_dialogue import spoken_roleplay_messages


DIFFICULTY_ROLEPLAY_RU = {
    "easy": "Лёгкая: если просьба конкретна и выполнима, соглашайся без искусственных преград.",
    "medium": "Средняя: у персонажа должна быть конкретная конкурирующая потребность, привычка или опасение. Не отказывайся от них только из-за одной вежливой просьбы. Назови настоящее затруднение и реагируй на реальные предложения игрока. Если оно устранено, соглашайся без искусственной задержки.",
    "hard": "Сложная: у персонажа несколько правдоподобных, независимо значимых возражений. Одного общего заверения мало для снятия всех. Пересматривай позицию по мере конкретных предложений и проверяемых уступок; не сопротивляйся ради числа ходов.",
    "extra_hard": "Очень сложная: устойчивые интересы с существенными последствиями или потерей доверия. Не капитулируй после первой красиво сформулированной границы; объясняй реальные препятствия и реагируй на их устранение. Допускай достижимый исход, когда ограничения действительно сняты.",
    "impossible": "Недостижимая цель: не соглашайся с объективно невозможным условием. Можно обсудить альтернативы, но они не равны достижению исходной цели.",
}
DIFFICULTY_ROLEPLAY_EN = {
    "easy": "Easy: agree to a specific feasible request promptly; do not invent obstacles.",
    "medium": "Medium: the character has a real competing need, habit or worry. One polite request alone does not remove it. State the concrete obstacle and respond to realistic proposals. Agree once resolved, never solely to add turns.",
    "hard": "Hard: multiple independently meaningful objections remain until addressed by specific feasible proposals; do not prolong resistance mechanically.",
    "extra_hard": "Very hard: deeply rooted interests, tangible consequences or strained trust. A well-phrased opening boundary alone need not persuade. Hold a reasoned position until major obstacles are materially resolved, not for a fixed number of turns.",
    "impossible": "Impossible: preserve the objectively unattainable condition. Discuss possible alternatives without pretending they achieve the original goal.",
}

GENERATOR_GUIDANCE_RU = (
    "Публичная цель игрока должна задавать проверяемое изменение поведения или "
    "конкретную договорённость, а не обязательное «признание права», изменение "
    "внутренних убеждений или чувств другого человека. Различай сложность через "
    "объективные и психологически правдоподобные причины сопротивления: easy — "
    "ясная осуществимая просьба; medium — реальный встречный интерес; hard — "
    "несколько независимых препятствий; extra_hard — существенные ставки и "
    "устойчивые ограничения; impossible — одно объективно недостижимое условие. "
    "Описывай это согласованно в opponent.goals, private_facts, hard_limits, "
    "concede_if, escalate_if. Не требуй минимального числа ходов и не добавляй "
    "случайной враждебности: после реального решения персонаж может согласиться."
)
GENERATOR_GUIDANCE_EN = (
    "Make the public player goal observable as a feasible change of behavior or a concrete "
    "agreement, NOT forced admission of a right, remorse, love or private belief. "
    "Difficulty must follow consistent character stakes: easy is a clear feasible "
    "request, medium has a genuine competing concern, hard has independently "
    "meaningful obstacles, very hard has significant lasting consequences and "
    "constraints, impossible has one objectively unattainable condition. Encode "
    "these consistently in opponent.goals, private_facts, hard_limits, concede_if "
    "and escalate_if. Never demand a fixed number of turns, baseless aggression, "
    "or agreement before the obstacles are actually addressed."
)


def live_generator_messages(options, repair=""):
    """Append quality constraints to the demo request, not the frozen template."""
    messages = generator_prompt(options, repair)
    language = options.get("language", "ru")
    if language not in {"ru", "en"}:
        raise ValueError("unsupported language")
    messages[-1]["content"] += "\n\n" + (GENERATOR_GUIDANCE_EN if language == "en" else GENERATOR_GUIDANCE_RU)
    return messages


def live_spoken_roleplay_messages(case, history, language="ru"):
    """Explicitly opt-in spoken style, preserving the historical original route."""
    messages = spoken_roleplay_messages(case, history, language)
    guidance = (DIFFICULTY_ROLEPLAY_EN if language == "en" else DIFFICULTY_ROLEPLAY_RU)[case["difficulty"]]
    messages[0]["content"] += "\n" + guidance
    return messages
