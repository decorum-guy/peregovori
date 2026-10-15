"""Separate style preparation after baseline, no model calls."""
import hashlib
import json
from pathlib import Path

import pytest

from app.prompts import roleplay_messages, ROLEPLAY_RULES
from app.providers import _mock_case
from app.spoken_dialogue import spoken_roleplay_messages, asterisk_stage_directions, SPOKEN_RULES, SPOKEN_DIALOGUE_VERSION


@pytest.mark.parametrize('language',['ru','en'])
def test_prepared_rule_only_appends_instruction_and_keeps_history(language):
    case=_mock_case({'scenario':'conflict_only','difficulty':'hard','conflict_type':'personal','student_side':'protect','language':language})
    history=[{'speaker':'opponent','text':case['opponent']['opening']},{'speaker':'player','text':'A human move.'}]
    original=roleplay_messages(case,history,language)
    prepared=spoken_roleplay_messages(case,history,language)
    assert prepared[0]['content']==original[0]['content']+'\n'+SPOKEN_RULES[language]
    assert prepared[1:]==original[1:]
    assert roleplay_messages(case,history,language)==original
    assert SPOKEN_DIALOGUE_VERSION=='spoken-dialogue-1.0'
    assert hashlib.sha256(ROLEPLAY_RULES.encode()).hexdigest()=='fe9f37b3d0d1c2989dd38971a194398f88b3e0b96bdf6aef926f7d76555a5656'


@pytest.mark.parametrize('text', ['*(вздыхает, теребит шарф)* Нет.', '*вздыхает* Нет.', '*(тише)* Нет.',
                                '*(sighs, adjusts scarf)* No.', '*smiles* I disagree.'])
def test_detects_directions_without_modifying_text(text):
    before=text
    assert len(asterisk_stage_directions(text))==1
    assert text==before


@pytest.mark.parametrize('text',['Нет, я не согласна.','No, I disagree.','Только *после* согласования.',
                               'Only *after* approval.','Она назвала неверное имя.','Я не буду вздыхать.'])
def test_ordinary_dialogue_and_emphasis_are_not_destructively_filtered(text):
    assert not asterisk_stage_directions(text)


def test_real_personal_baseline_has_nine_stage_directions_and_remains_unmodified():
    path=Path(__file__).resolve().parents[3]/'docs/live_claude_playtest/2026-10-14/02-personal-public.json'
    before=path.read_bytes();snapshot=json.loads(before)
    matches=[direction for m in snapshot['messages'] if m['speaker']=='opponent'
             for direction in asterisk_stage_directions(m['text'])]
    assert len(matches)==9
    assert path.read_bytes()==before


def test_fact_and_style_defects_are_independent_in_frozen_evidence():
    path=Path(__file__).resolve().parents[3]/'docs/live_claude_playtest/2026-10-14/02-personal-public.json'
    replies=[m['text'] for m in json.loads(path.read_text())['messages'] if m['speaker']=='opponent']
    invented=next(text for text in replies if 'в институт сумки таскал' in text)
    assert not asterisk_stage_directions(invented)  # Spoken-only format does not prove factual correctness.
    assert 'болела' in invented



@pytest.mark.parametrize('language', ['ru', 'en'])
@pytest.mark.parametrize('difficulty', ['easy', 'medium', 'hard', 'extra_hard', 'impossible'])
def test_roleplayer_receives_distinct_causal_difficulty_instructions(language, difficulty):
    from app.prompts import DIFFICULTY_ROLEPLAY_EN, DIFFICULTY_ROLEPLAY_RU
    case = _mock_case({'scenario': 'conflict_only', 'difficulty': difficulty,
                       'conflict_type': 'personal', 'student_side': 'protect', 'language': language})
    instruction = (DIFFICULTY_ROLEPLAY_EN if language == 'en' else DIFFICULTY_ROLEPLAY_RU)[difficulty]
    prompts = spoken_roleplay_messages(case, [], language)
    assert instruction in prompts[0]['content']
    assert case['opponent']['hard_limits']
    assert prompts[0]['role'] == 'system'


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_case_generator_requests_observable_goals_and_real_constraints(language):
    from app.prompts import generator_prompt
    options = {'scenario': 'conflict_only', 'difficulty': 'extra_hard',
               'conflict_type': 'personal', 'student_side': 'protect', 'language': language}
    messages = generator_prompt(options)
    guidance = messages[-1]['content']
    assert ('проверяемое изменение' if language == 'ru' else 'observable as a feasible change') in guidance
    assert 'concede_if' in guidance
    assert 'hard_limits' in guidance



def test_unknown_language_is_rejected():
    with pytest.raises(ValueError):spoken_roleplay_messages({},[],'fr')
