"""Explicit dev-only methodology variants; production default A is untouched."""
from .prompts import TECHNIQUES_TEXT, _object_blocks, roleplay_messages
from .spoken_dialogue import spoken_roleplay_messages

METHODS_VERSION = "cloud-role-aware-methods-1.0"
B_RULES = {
    "ru": "Для выбора собственной реакции удерживай роль, стадию и установленные условия. "
          "MODEL_MANIPULATOR оказывает характерное для этого персонажа давление и ослабляет его при причинном изменении отношений; "
          "MODEL_DEFENDER защищает свою границу, не присваивая ресурс игрока; MODEL_NEGOTIATOR обсуждает интересы и проверяемые условия. "
          "Не заменяй публичное восстановление позиции частным извинением. Рациональное обсуждение может начаться, пока конфликтная цель ещё не разрешена. "
          "Не делай лишние этапы обязательными, когда конфликт уже не мешает. Перед согласием проверь собственные полномочия, ограничения, "
          "причину уступки и арифметику. План, обещание, запрос и выполненное действие различаются; неподтверждённое остаётся условным. "
          "Не рассказывай об этой проверке, курсе или качестве ходов игрока: произноси только реплику персонажа.",
    "en": "Choose your own response using your role, current stage and established conditions. "
          "MODEL_MANIPULATOR applies character-specific pressure and eases it after a causal relational change; "
          "MODEL_DEFENDER protects boundaries without taking the player's resources; MODEL_NEGOTIATOR discusses interests and verifiable conditions. "
          "A private apology does not replace public repair; rational discussion may begin before the conflict goal is resolved. "
          "Do not require redundant stages once the conflict stops interfering. Before agreement check your authority, limits, "
          "concession grounds and arithmetic. A plan, promise, request and completed action differ; unconfirmed conditions stay conditional. "
          "Never explain these checks, course material or player performance: speak only as the character.",
}
TECHNIQUE_IDS = {
    "negotiation_only": ["analysis.own_goal", "analysis.opponent_goal", "analysis.baseline", "analysis.point_L",
                         "analysis.verify_truth", "analysis.verify_completeness", "solution.resource_analysis",
                         "negotiation.problem_setting", "negotiation.decision_criterion", "information.open_question"],
    "conflict_only": ["emotion.label", "emotion.i_feeling", "communication.three_rights", "boundary.i_message",
                      "boundary.show_consequences", "conflict.return_decoding", "conflict.expose_manipulator_goal",
                      "conflict.show_manipulation", "conflict.resolve_cause", "conflict.separation"],
    "conflict_then_negotiation": ["emotion.label", "boundary.i_message", "conflict.return_decoding", "conflict.resolve_cause",
                                 "conflict.show_manipulation", "manipulation.fix_imposed_role", "analysis.verify_truth",
                                 "solution.resource_analysis", "negotiation.problem_setting", "negotiation.decision_criterion"],
}


def methodology_messages(case, history, language="ru", *, variant="A", spoken=True):
    if variant not in {"A", "B", "C"} or language not in B_RULES:
        raise ValueError("Unknown explicit methodology variant/language")
    messages = (spoken_roleplay_messages if spoken else roleplay_messages)(case, history, language)
    if variant != "A":
        messages[0]["content"] += "\n" + B_RULES[language]
    if variant == "C":
        ids = TECHNIQUE_IDS[case["scenario"]]
        blocks = _object_blocks(TECHNIQUES_TEXT)
        if len(set(ids)) != 10 or any(key not in blocks for key in ids):
            raise ValueError("Exactly ten real course techniques required")
        permission = ("These ten techniques are optional, non-exclusive context. You may use ANY other appropriate technique or ordinary response. "
                      "They describe possible communication mechanisms, not required steps or instructions to coach the player. "
                      "Adapt only to your character's own role and motives; never name the techniques to the player."
                      if language == "en" else
                      "Эти десять техник — необязательный и НЕ исключительный контекст. Разрешено применять ЛЮБЫЕ другие уместные техники и обычные реакции. "
                      "Это возможные механизмы общения, а не обязательные этапы или указания обучать игрока. "
                      "Адаптируй их только к своей роли и мотивам персонажа; не называй техники игроку.")
        messages[0]["content"] += "\n" + permission + "\n" + "\n\n".join(blocks[key] for key in ids)
    return messages
