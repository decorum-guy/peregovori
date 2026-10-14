"""Offline, searchable PDF from the same explicit public whitelist as the UI.

No store/provider/runtime-case access belongs in this module.
"""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ASSETS = Path(__file__).with_name("export_assets")
pdfmetrics.registerFont(TTFont("CaseSans", str(ASSETS / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("CaseSansBold", str(ASSETS / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("CaseSans", normal="CaseSans", bold="CaseSansBold", italic="CaseSans", boldItalic="CaseSansBold")
NAVY, RUST, INK = map(colors.HexColor, ("#243B5A", "#AE432F", "#202B3E"))


def export_filename(snapshot) -> str:
    # Title/player name never enters a header or filename.
    token = re.sub(r"[^a-zA-Z0-9-]", "", snapshot["id"])[:40] or "session"
    return "line-of-decision-%s.pdf" % token


def render_pdf(snapshot) -> bytes:
    english = snapshot["settings"].get("language") == "en"
    def label(ru, en):
        return en if english else ru

    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
                           topMargin=31 * mm, bottomMargin=23 * mm,
                           title=snapshot["case"]["title"], author=label("Линия решения", "Line of Decision"))
    body = ParagraphStyle("Body", fontName="CaseSans", fontSize=10, leading=15, textColor=INK,
                          spaceAfter=9, alignment=TA_LEFT, splitLongWords=True, allowWidows=0, allowOrphans=0)
    title = ParagraphStyle("Title", parent=body, fontName="CaseSansBold", fontSize=23, leading=29, textColor=NAVY, spaceAfter=16)
    heading = ParagraphStyle("Heading", parent=body, fontName="CaseSansBold", fontSize=15, leading=21,
                             textColor=NAVY, spaceBefore=13, spaceAfter=10, keepWithNext=True)
    caption = ParagraphStyle("Caption", parent=body, fontName="CaseSansBold", fontSize=9, leading=13,
                             textColor=RUST, spaceBefore=8, spaceAfter=5, keepWithNext=True)
    muted = ParagraphStyle("Muted", parent=body, fontSize=8, leading=12, textColor=colors.HexColor("#596477"))
    story = []
    def paragraph(text, style=body):
        # Escape all user/model markup; retain line breaks and safely remove control chars.
        text = "".join(c for c in str(text) if ord(c) >= 32 or c in "\n\t")
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), style))
    def field(name, value):
        if value:
            paragraph(name, caption)
            paragraph(value)

    case = snapshot["case"]
    paragraph(label("КЕЙС И ДИАЛОГ", "CASE AND DIALOGUE"), caption)
    paragraph(case["title"], title)
    date = datetime.fromisoformat(snapshot["created_at"]).strftime("%d.%m.%Y")
    paragraph(label("Дата сессии: ", "Session date: ") + date + " (UTC)", muted)
    if snapshot["provider_mode"] == "test_mock":
        paragraph(label("Тестовая симуляция: ответы не получены от живой модели.", "Test simulation: responses are not from a live model."), muted)
    scenarios = {"conflict_only": ("Конфликт", "Conflict"), "negotiation_only": ("Переговоры", "Negotiation"),
                 "conflict_then_negotiation": ("Конфликт + переговоры", "Conflict + negotiation")}
    difficulties = {"easy": ("Лёгкая", "Easy"), "medium": ("Средняя", "Medium"), "hard": ("Сложная", "Hard"),
                    "extra_hard": ("Очень сложная", "Very hard"), "impossible": ("Желаемый исход закрыт", "Desired outcome unavailable")}
    field(label("Формат и сложность", "Format and difficulty"), label(*scenarios[case["scenario"]]) + " · " + label(*difficulties[snapshot["settings"]["difficulty"]]))
    field(label("Контекст", "Context"), case["context"])
    field(label("Ваша роль", "Your role"), case["student_role"])
    field(label("Собеседник", "Conversation partner"), snapshot["opponent"]["name"] + " · " + snapshot["opponent"]["role"])
    for key, ru, en in (("student_goal", "Ваша задача", "Your task"),
                        ("player_conflict_goal", "Цель на конфликт", "Conflict goal"),
                        ("negotiation_topic", "Тема на переговоры", "Negotiation topic")):
        field(label(ru, en), case.get(key))
    paragraph(label("Известные факты", "Known facts"), caption)
    for fact in case["known_facts"]:
        paragraph("• " + fact)
    if case["participants"]:
        paragraph(label("Участники", "Participants"), caption)
        for participant in case["participants"]:
            paragraph(participant["name"] + " · " + participant["role"])

    paragraph(label("Полная переписка", "Full conversation"), heading)
    player = snapshot["settings"].get("player_name") or label("Вы", "You")
    statuses = {"pending": ("Ответ ожидается", "Reply pending"), "failed": ("Ответ не получен", "Reply not received"),
                "cancelled": ("Сессия завершена до ответа", "Session finished before reply")}
    for index, message in enumerate(snapshot["messages"], 1):
        speaker = player if message["speaker"] == "player" else snapshot["opponent"]["name"]
        role = label("Игрок", "Player") if message["speaker"] == "player" else label("Собеседник", "Partner")
        role_style = ParagraphStyle("Role", parent=caption, textColor=RUST if message["speaker"] == "player" else NAVY)
        paragraph("%02d · %s · %s" % (index, role, speaker), role_style)
        paragraph(message["text"])
        if message["delivery_status"] in statuses:
            paragraph(label(*statuses[message["delivery_status"]]), muted)
        story.append(Spacer(1, 3 * mm))

    report = snapshot.get("debrief") if snapshot.get("debrief_status") == "complete" else None
    if report:
        story.append(PageBreak())
        paragraph(label("ПОСЛЕ ДИАЛОГА", "AFTER THE DIALOGUE"), caption)
        paragraph(label("Ваш разбор", "Your review"), title)
        paragraph(label("Учебные рекомендации независимого прототипа. Это не официальный балл.",
                        "Educational guidance from an independent prototype. This is not an official score."), muted)
        field(label("Что произошло", "What happened"), report["summary"])
        for key, ru, en in (("strengths", "Сильные действия", "Strengths"), ("risks", "Что можно изменить", "What could change")):
            if report[key]:
                paragraph(label(ru, en), heading)
                for point in report[key]:
                    paragraph("«" + point["quote"] + "»")
                    paragraph(point["explanation"])
        field(label("Следующий ход", "Next move"), report["next_step"])
        field(label("Пример формулировки", "Example wording"), report.get("example_phrase"))

    def page_frame(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.drawImage(str(ASSETS / "next-move.png"), 21 * mm, height - 24 * mm, 14 * mm, 14 * mm, mask="auto")
        canvas.setFont("CaseSansBold", 11)
        canvas.setFillColor(NAVY)
        canvas.drawString(39 * mm, height - 17 * mm, label("ЛИНИЯ РЕШЕНИЯ", "LINE OF DECISION"))
        canvas.setStrokeColor(colors.HexColor("#DCE0E7"))
        canvas.line(22 * mm, height - 26 * mm, width - 22 * mm, height - 26 * mm)
        canvas.line(22 * mm, 18 * mm, width - 22 * mm, 18 * mm)
        canvas.setFont("CaseSans", 8)
        canvas.setFillColor(INK)
        canvas.drawString(22 * mm, 12 * mm, label("Независимый концепт", "Independent concept"))
        canvas.drawRightString(width - 22 * mm, 12 * mm, label("Страница ", "Page ") + str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return stream.getvalue()
