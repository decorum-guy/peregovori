from __future__ import annotations

import re
import unicodedata
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


Scenario = Literal["conflict_only", "negotiation_only", "conflict_then_negotiation"]
Difficulty = Literal["easy", "medium", "hard", "extra_hard", "impossible"]
ConflictType = Literal["personal", "public", "mixed", "none"]
Category = Literal["MODEL_MANIPULATOR", "MODEL_DEFENDER", "MODEL_NEGOTIATOR"]
StudentSide = Literal["protect", "pressure"]
EngineId = Literal["premium", "lora"]
Language = Literal["ru", "en"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Participant(StrictModel):
    name: StrictStr = Field(min_length=1, max_length=100)
    role: StrictStr = Field(min_length=1, max_length=180)


class PublicCase(StrictModel):
    title: StrictStr = Field(min_length=1, max_length=180)
    context: StrictStr = Field(min_length=1, max_length=3000)
    student_role: StrictStr = Field(min_length=1, max_length=180)
    student_goal: Optional[StrictStr] = Field(default=None, max_length=500)
    negotiation_topic: Optional[StrictStr] = Field(default=None, max_length=500)
    player_conflict_goal: Optional[StrictStr] = Field(default=None, max_length=500)
    known_facts: List[StrictStr] = Field(min_length=1, max_length=12)
    participants: List[Participant] = Field(default_factory=list, max_length=8)

    @field_validator("known_facts")
    @classmethod
    def facts_are_nonempty(cls, facts: List[str]) -> List[str]:
        if any(not fact.strip() for fact in facts):
            raise ValueError("known_facts must not contain blank entries")
        return facts


class World(StrictModel):
    facts: List[StrictStr] = Field(min_length=1, max_length=16)
    unknowns: List[StrictStr] = Field(default_factory=list, max_length=12)


class Opponent(StrictModel):
    name: StrictStr = Field(min_length=1, max_length=100)
    role: StrictStr = Field(min_length=1, max_length=180)
    opening: StrictStr = Field(min_length=1, max_length=1500)
    private_facts: List[StrictStr] = Field(default_factory=list, max_length=12)
    goals: List[StrictStr] = Field(min_length=1, max_length=8)
    hard_limits: List[StrictStr] = Field(default_factory=list, max_length=12)
    concede_if: List[StrictStr] = Field(min_length=1, max_length=8)
    escalate_if: List[StrictStr] = Field(default_factory=list, max_length=8)
    initial_emotion: StrictStr = Field(min_length=1, max_length=180)


class Teaching(StrictModel):
    perspective: Literal["student", "model_character", "not_applicable"]
    conflict_type: ConflictType
    negotiation_topic: Optional[StrictStr] = Field(default=None, max_length=500)
    conflict_goal: Optional[StrictStr] = Field(default=None, max_length=500)
    decoding: Optional[StrictStr] = Field(default=None, max_length=300)
    initial_stage: Literal["emotion", "show_boundary", "defend_boundary", "stage4", "negotiation"]
    focus_techniques: List[StrictStr] = Field(min_length=1, max_length=8)
    acceptable_outcomes: List[StrictStr] = Field(min_length=1, max_length=8)


class RuntimeCase(StrictModel):
    schema_version: Literal["runtime-1.0"] = "runtime-1.0"
    category: Category
    difficulty: Difficulty
    scenario: Scenario
    conflict_type: ConflictType
    public: PublicCase
    world: World
    opponent: Opponent
    teaching: Teaching

    @model_validator(mode="after")
    def validate_semantics(self) -> "RuntimeCase":
        p = self.public
        t = self.teaching
        if self.scenario == "negotiation_only":
            if self.category != "MODEL_NEGOTIATOR" or self.conflict_type != "none":
                raise ValueError("negotiation_only requires MODEL_NEGOTIATOR and conflict_type=none")
            if not p.negotiation_topic or p.player_conflict_goal is not None:
                raise ValueError("negotiation_only requires a public topic and no player conflict goal")
            if t.conflict_goal is not None or t.perspective != "not_applicable":
                raise ValueError("negotiation_only teaching must not contain a conflict goal")
        else:
            if self.category == "MODEL_NEGOTIATOR" or self.conflict_type == "none":
                raise ValueError("conflict scenarios require a conflict role and type")
            if not p.player_conflict_goal:
                raise ValueError("conflict scenarios require the player's own conflict goal")
            if self.scenario == "conflict_then_negotiation" and not p.negotiation_topic:
                raise ValueError("conflict_then_negotiation requires a separate negotiation topic")
            if self.category == "MODEL_DEFENDER" and t.perspective != "model_character":
                raise ValueError("MODEL_DEFENDER teaching perspective must be model_character")
            if self.category == "MODEL_MANIPULATOR" and t.perspective != "student":
                raise ValueError("MODEL_MANIPULATOR teaching perspective must be student")
            if self.category == "MODEL_DEFENDER" and t.conflict_goal:
                left = _meaningful_tokens(p.player_conflict_goal or "")
                right = _meaningful_tokens(t.conflict_goal)
                overlap = len(left & right) / max(1, len(left | right))
                if overlap > 0.68 and len(left & right) >= 4:
                    raise ValueError("the player's public goal appears to copy the model character's hidden goal")
        if self.conflict_type != t.conflict_type:
            raise ValueError("runtime and teaching conflict_type do not match")
        if self.scenario != "negotiation_only" and self.conflict_type in {"public", "mixed"} and not p.participants:
            raise ValueError("public and mixed conflict cases must name at least one known audience participant")
        if self.scenario == "negotiation_only" and t.negotiation_topic is None:
            raise ValueError("negotiation_only requires a teaching negotiation topic")
        if self.scenario == "conflict_then_negotiation" and t.negotiation_topic is None:
            raise ValueError("conflict_then_negotiation requires a teaching negotiation topic")
        if self.scenario == "conflict_then_negotiation" and p.negotiation_topic and p.player_conflict_goal:
            public_tokens = _meaningful_tokens(p.negotiation_topic)
            goal_tokens = _meaningful_tokens(p.player_conflict_goal)
            overlap = len(public_tokens & goal_tokens) / max(1, len(public_tokens | goal_tokens))
            if overlap > 0.72 and len(public_tokens & goal_tokens) >= 4:
                raise ValueError("negotiation topic and player conflict goal must be distinct")
        return self


class SessionOptions(StrictModel):
    language: Language = "ru"
    scenario: Scenario
    conflict_type: Optional[Literal["personal", "public", "mixed"]] = None
    difficulty: Difficulty
    student_side: Optional[StudentSide] = None
    sphere: Literal["work", "family", "study", "friends", "custom"]
    custom_topic: Optional[StrictStr] = Field(default=None, max_length=240)
    player_name: Optional[StrictStr] = Field(default=None, max_length=60)
    engine_id: EngineId = "premium"

    @model_validator(mode="after")
    def validate_conditional_options(self) -> "SessionOptions":
        if self.language == "en" and self.engine_id == "lora":
            raise ValueError("English games require the OpenRouter model. Qwen is available for Russian games only.")
        if self.scenario == "negotiation_only":
            if self.conflict_type is not None or self.student_side is not None:
                raise ValueError("conflict type and student side are not sent for pure negotiations")
        elif self.conflict_type is None or self.student_side is None:
            raise ValueError("conflict scenarios require both conflict_type and student_side")
        if self.sphere == "custom" and (self.custom_topic is None or not self.custom_topic.strip()):
            raise ValueError("Enter your topic for the Other setting." if self.language == "en" else "Укажите вашу тему для сферы «Другое».")
        return self


class MessageRequest(StrictModel):
    text: StrictStr = Field(min_length=1, max_length=20000)
    request_id: StrictStr = Field(min_length=8, max_length=80)

    @field_validator("text")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value.strip()


class CompletionDismissRequest(StrictModel):
    reply_id: StrictStr = Field(min_length=1, max_length=100)


class DebriefPoint(StrictModel):
    quote: StrictStr = Field(min_length=1, max_length=1200)
    explanation: StrictStr = Field(min_length=1, max_length=1200)


class DebriefReport(StrictModel):
    summary: StrictStr = Field(min_length=1, max_length=1500)
    strengths: List[DebriefPoint] = Field(default_factory=list, max_length=4)
    risks: List[DebriefPoint] = Field(default_factory=list, max_length=4)
    next_step: StrictStr = Field(min_length=1, max_length=1000)
    example_phrase: Optional[StrictStr] = Field(default=None, max_length=500)


def _meaningful_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return {token for token in re.findall(r"[\w]+", normalized, flags=re.UNICODE) if len(token) > 3}
