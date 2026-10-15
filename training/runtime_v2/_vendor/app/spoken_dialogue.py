"""Prepared RU/EN spoken-only contract. Not enabled in the live baseline runtime."""
from __future__ import annotations

import re

from .prompts import roleplay_messages


SPOKEN_DIALOGUE_VERSION = "spoken-dialogue-1.0"
SPOKEN_RULES = {
    "ru": "Сообщение состоит только из слов, которые твой персонаж непосредственно произносит собеседнику. "
          "Не добавляй ремарки в звёздочках или скобках, описания действий, жестов, мимики, дыхания и повествование от третьего лица. "
          "Выражай эмоции выбором слов, несогласием, сопротивлением и изменением позиции в самом диалоге; "
          "сохраняй естественную эмоциональную динамику, границы персонажа и правило одного вопроса, без оценки игрока и педагогических советов.",
    "en": "Return only words your character directly speaks to the other person. "
          "Do not add asterisk or parenthetical stage directions, actions, gestures, facial expressions, breathing descriptions or third-person narration. "
          "Express emotions through wording, disagreement, resistance and changes of position in the dialogue itself; "
          "preserve natural emotional dynamics, character boundaries and the one-question rule, without coaching.",
}


def spoken_roleplay_messages(case, history, language="ru"):
    """Explicit preparation entrypoint; never silently replaces the original serializer."""
    if language not in SPOKEN_RULES:
        raise ValueError("Spoken dialogue supports ru and en.")
    messages = roleplay_messages(case, history, language)
    messages[0]["content"] += "\n" + SPOKEN_RULES[language]
    return messages


_ASTERISKS = re.compile(r"\*\(([^*\n]+)\)\*|\*([^*\n]+)\*")
_ACTION = re.compile(r"\b(?:вздыхает|выдохнула|кивает|улыбается|усмехается|теребит|садится|встаёт|"
                     r"смотрит|отводит|останавливается|поправляет|поджимает|помолчав|sighs|sighing|"
                     r"smiles|smiling|nods|nodding|shrugs|looks|breathes|pauses|sits|stands|leans|turns)\b", re.I)


def asterisk_stage_directions(text):
    """QA findings only: never strip dialogue or initiate a model retry.

    Recognizes parenthesized asterisk directions and common action verbs in bare
    asterisks. Not a general narration classifier. Ordinary emphasis is preserved.
    """
    return [match.group(0) for match in _ASTERISKS.finditer(text)
            if match.group(1) is not None or _ACTION.search(match.group(2) or "")]
