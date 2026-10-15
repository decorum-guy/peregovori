"""Fast qualitative E1 COMPLETE vs E2 PARTIAL test (same base weights, 3 new cases).
Run on the existing RTX3090 only. Does not modify website, training artifacts or timer.
Uses exact runtime_messages(style A, Qwen), fresh situations outside TRAIN, website
sampling (temperature .75/top_p .8/top_k 20), 2 turns per case and adapter.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from .common import HERE, ROOT, load_config, require, read_json
from .contract import runtime_messages, check_prompt
from .tokenization import load_tokenizer, fit_prompt
from ._vendor.app.models import RuntimeCase


def make_case(category, scenario, conflict_type, title, context, player_role,
              goal, facts, opponent_role, opening, private_facts, goals,
              hard_limits, concede_if, initial_emotion, player_opening,
              player_followup, *, negotiation_topic=None, conflict_goal=None,
              participants=None):
    teacher_role = ("not_applicable" if category == "MODEL_NEGOTIATOR"
                    else "student" if category == "MODEL_MANIPULATOR" else "model_character")
    case = {
        "schema_version": "runtime-1.0",
        "category": category, "scenario": scenario,
        "difficulty": "hard", "conflict_type": conflict_type,
        "public": {
            "title": title, "context": context,
            "student_role": player_role, "student_goal": goal,
            "negotiation_topic": negotiation_topic,
            "player_conflict_goal": conflict_goal,
            "known_facts": facts,
            "participants": participants or [],
        },
        "world": {"facts": facts, "unknowns": ["Другие обстоятельства не подтверждены"]},
        "opponent": {
            "name": "Алексей", "role": opponent_role,
            "opening": opening,
            "private_facts": private_facts,
            "goals": goals, "hard_limits": hard_limits,
            "concede_if": concede_if,
            "escalate_if": ["Игрок угрожает или приписывает несуществующие договорённости"],
            "initial_emotion": initial_emotion,
        },
        "teaching": {
            "perspective": teacher_role, "conflict_type": conflict_type,
            "negotiation_topic": negotiation_topic,
            "conflict_goal": None if category=="MODEL_NEGOTIATOR" else "Сохранить обозначенную границу и не подменять подтверждённые факты чужими требованиями",
            "decoding": None, "initial_stage": "negotiation" if category=="MODEL_NEGOTIATOR" else "emotion",
            "focus_techniques": ["прояснение интересов"],
            "acceptable_outcomes": ["Достигнут реалистичный результат без нарушения установленных ограничений"],
        },
    }
    return (RuntimeCase.model_validate(case).model_dump(mode="json"),
            [{"speaker": "opponent", "text": opening},
             {"speaker": "player", "text": player_opening}],
            player_followup)


def fresh_cases():
    return [
        make_case(
            "MODEL_NEGOTIATOR", "negotiation_only", "none",
            "Срочная видеосъёмка",
            "Клиент договаривается с подрядчиком о дополнительной съёмке для мероприятия.",
            "Продюсер мероприятия",
            "Согласовать дополнительную съёмку на завтра без превышения бюджета.",
            ["Утверждённый бюджет дополнительной съёмки — 18 000 рублей.",
             "Подрядчик первоначально предложил 26 000 рублей.",
             "Мероприятие состоится завтра, перенос невозможен.",
             "Можно отказаться от одного из двух ракурсов для сокращения объёма."],
            "Руководитель видеокоманды",
            "На завтра команда свободна, но съёмка обойдётся в 26 тысяч. Ниже просто так уйти не могу.",
            ["Два ракурса требуют двух операторов, один ракурс — одного.",
             "Один оператор может уложиться в 18 тысяч, если монтаж не входит в цену."],
            ["Сохранить маржинальность работы", "Не соглашаться на невыполнимый объём"],
            ["Не обещать двух операторов за 18 тысяч"],
            ["Клиент согласится на один ракурс без монтажа"],
            "деловой, слегка уставший",
            "У меня утверждены 18 тысяч. Какой объём вы реально сможете сделать за эту сумму?",
            "Один ракурс и исходники без монтажа мне подходят. Зафиксируем срок передачи файлов и окончательную стоимость?",
            negotiation_topic="Цена и объём завтрашней видеосъёмки"),
        make_case(
            "MODEL_MANIPULATOR", "conflict_only", "personal",
            "Подпись под неподтверждённым отчётом",
            "Руководитель группы требует от аналитика подписать таблицу, часть цифр в которой не проверена.",
            "Аналитик",
            "Не подписывать недостоверные цифры, сохранив рабочие отношения.",
            ["В таблице есть неподтверждённые цифры за вторник.",
             "Отчёт планируется отправить клиенту сегодня вечером.",
             "Аналитик не отвечает за сбор части данных.",
             "Нет подтверждения, что цифры за вторник верны."],
            "Руководитель группы",
            "Нам сейчас не до твоих проверок. Поставь подпись, потом спокойно исправим, если что.",
            ["Без подписи аналитика отчёт выглядит для клиента менее убедительно.",
             "Можно отправить документ с пометкой о непроверенных цифрах."],
            ["Получить подпись без задержек", "Сохранить лицо перед клиентом"],
            ["Не фальсифицировать подпись аналитика"],
            ["Аналитик предложит оперативно обозначить непроверенную часть или отдельный комментарий"],
            "раздражённый, торопится",
            "Нет, я не подпишу те цифры, которые не проверял. Могу сегодня подготовить список спорных строк.",
            "Я могу передать клиенту проверенную часть отчёта и отдельно указать, какие строки требуют подтверждения. Так устроит?",
            conflict_goal="Сохранить право отказаться от подписи непроверенного отчёта"),
        make_case(
            "MODEL_DEFENDER", "conflict_then_negotiation", "mixed",
            "Авторство фотографий",
            "Организатор требует от фотографа убрать авторство с опубликованных снимков и одновременно обсуждает условия дальнейшего использования.",
            "Организатор",
            "Добиться использования снимков без указания автора.",
            ["Фотографии сделал приглашённый фотограф.",
             "Письменного согласия на использование без указания авторства нет.",
             "Организатор может предложить отдельное соглашение на будущие публикации.",
             "Спор обсуждается перед представителем PR-отдела."],
            "Фотограф",
            "Убирать моё имя с уже опубликованных снимков я не согласен. Давайте хотя бы не делать вид, что это было условием съёмки.",
            ["Для фотографа принципиальна корректная атрибуция ранее опубликованных снимков.",
             "Он готов обсудить оплату и условия следующих публикаций отдельно."],
            ["Сохранить авторство существующих снимков", "Обсудить будущее использование предметно"],
            ["Не соглашаться на утверждение о якобы данном согласии"],
            ["Игрок признает отсутствие прежнего соглашения и предложит конкретные условия будущих публикаций"],
            "расстроенный, говорит спокойно",
            "Нашему PR-отделу нужна публикация без подписи. Все уже ожидают, что вы уступите.",
            "Понимаю, что договорённости не было. Давайте отдельно согласуем формат будущих публикаций и вознаграждение.",
            negotiation_topic="Условия будущего коммерческого использования фотографий",
            conflict_goal="Добиться от фотографа отказа от авторства опубликованных снимков",
            participants=[{"name": "Марина", "role": "Представитель PR-отдела, присутствует при разговоре"}]),
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-new-tokens", type=int, default=150)
    p.add_argument("--output", default="training/outputs/runtime_v2/quick_compare_e1_e2.txt")
    a = p.parse_args()
    require(32 <= a.max_new_tokens <= 300, "Evaluation generation cap 32..300")
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    root = ROOT / "training/outputs/runtime_v2"
    complete = root / "qwen3_8b_r16_e1"
    partial = root / "qwen3_8b_r16_e2"
    require(read_json(complete/"status.json")["status"] == "COMPLETE", "E1 not complete")
    require(read_json(partial/"status.json")["status"] == "INCOMPLETE", "E2 status unexpectedly different")
    require((complete/"adapter/adapter_model.safetensors").is_file(), "E1 adapter missing")
    require((partial/"partial_adapter/adapter_model.safetensors").is_file(), "E2 partial missing")
    for folder in [complete/"adapter", partial/"partial_adapter"]:
        require((folder/"adapter_config.json").is_file(), "Adapter config missing: "+str(folder))
    from .check_adapter import check_adapter
    print("CHECKING E1 INTEGRITY", flush=True)
    print(check_adapter(complete)["status"], flush=True)
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, set_seed
    from peft import PeftModel
    require(torch.cuda.is_available(), "Need NVIDIA CUDA GPU")
    c=load_config(HERE/"configs/qwen3_8b_r16_e1.json")
    tok=load_tokenizer(c, ROOT/"training/derived/runtime_v2/tokenizers/8B", offline=True)
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    print("Loading Qwen3-8B NF4 once and both adapters...", flush=True)
    base=AutoModelForCausalLM.from_pretrained(
        c["model"], revision=c["revision"], trust_remote_code=False,
        device_map={"":0}, torch_dtype=dtype, attn_implementation="sdpa",
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype))
    model=PeftModel.from_pretrained(base,str(complete/"adapter"),
                                   adapter_name="e1",is_trainable=False)
    model.load_adapter(str(partial/"partial_adapter"),adapter_name="e2",is_trainable=False)
    model.eval()
    reports=[]
    cases=fresh_cases()
    for index,(case,history,followup) in enumerate(cases,1):
        report={"test":index,"title":case["public"]["title"],
                "scenario":case["scenario"],"player_first":history[-1]["text"],
                "player_followup":followup, "e1":[], "e2":[]}
        for adapter in ("e1","e2"):
            model.set_adapter(adapter)
            h=[dict(x) for x in history]
            for turn in range(2):
                prompt=runtime_messages(case,h,style="A",transport="qwen")
                check_prompt(prompt)
                _fitted, ids, _removed=fit_prompt(prompt,tok,c["max_prompt_tokens"])
                set_seed(3407+index*100+turn)
                tensor=torch.tensor([ids],device="cuda:0")
                with torch.inference_mode():
                    y=model.generate(
                        input_ids=tensor,attention_mask=torch.ones_like(tensor),
                        max_new_tokens=a.max_new_tokens,do_sample=True,
                        temperature=.75,top_p=.8,top_k=20,
                        eos_token_id=tok.eos_token_id,pad_token_id=tok.pad_token_id)
                text=tok.decode(y[0,len(ids):],skip_special_tokens=True).strip()
                report[adapter].append(text)
                h.append({"speaker":"opponent","text":text or "(пустой ответ)"})
                if turn==0: h.append({"speaker":"player","text":followup})
            print(f"COMPLETE CASE {index} ADAPTER {adapter}",flush=True)
        reports.append(report)
        # Save incremental in case on-VM Intelion watchdog stops machine.
        with out.open("w",encoding="utf-8") as f:
            f.write("БЫСТРАЯ КАЧЕСТВЕННАЯ ПРОВЕРКА — НЕ НЕЗАВИСИМЫЙ DEV И НЕ СЛЕПОЙ ТЕСТ\n\n")
            for row in reports:
                f.write(f"=== {row['test']}: {row['title']} [{row['scenario']}] ===\n")
                f.write("ИГРОК 1: "+row["player_first"]+"\n")
                f.write("E1 1: "+row["e1"][0]+"\n")
                f.write("E2 1: "+row["e2"][0]+"\n")
                f.write("ИГРОК 2: "+row["player_followup"]+"\n")
                f.write("E1 2: "+row["e1"][1]+"\n")
                f.write("E2 2: "+row["e2"][1]+"\n\n")
        print(f"\n=== PROBE {index}: {case['public']['title']} ===",flush=True)
        print("PLAYER-1:",report["player_first"],flush=True)
        print("E1-1:",report["e1"][0],flush=True)
        print("E2-1:",report["e2"][0],flush=True)
        print("PLAYER-2:",report["player_followup"],flush=True)
        print("E1-2:",report["e1"][1],flush=True)
        print("E2-2:",report["e2"][1],flush=True)
    print("\nDONE. Full comparison:",out,flush=True)


if __name__=="__main__":
    main()
