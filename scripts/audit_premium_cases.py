"""One optional independent blind semantic audit of saved paid cases; no regeneration."""
import argparse
import asyncio
import json
import random
from compare_premium_pipeline import Runner, PRIVATE, MODELS, SESSIONS, load_session, fingerprint
from app.prompts import RUNTIME_SPEC
from app.service import _all_strings, _hidden_leak


async def run():
    runner = Runner()
    candidates = []
    for scenario in SESSIONS:
        case = load_session(scenario)["case"]
        candidates.append({"model": MODELS[0], "case": case, "origin": "historical-paid"})
    for row in runner.budget.rows():
        if row["purpose"] == "case" and row["status"] == "accepted":
            case = json.loads((PRIVATE / (row["id"] + ".json")).read_text())["parsed"]
            candidates.append({"model": row["actual_model"], "case": case, "origin": row["id"]})
    random.Random(141026).shuffle(candidates)
    aliases = [{"alias": "G%02d" % (i+1), "case": row["case"]} for i, row in enumerate(candidates)]
    (PRIVATE / "generator-audit-key.json").write_text(json.dumps({a["alias"]: {
        "model": c["model"], "origin": c["origin"], "case_sha256": fingerprint(c["case"])}
        for a, c in zip(aliases, candidates)}, indent=2))
    messages = [{"role": "system", "content": "Ты независимый ревьюер качества вымышленных игровых кейсов. Модели-авторы скрыты. "
                 "Не разыгрывай диалог, не оценивай несуществующего игрока. Верни только JSON."},
                {"role": "user", "content": "Проверь все кейсы по логике мира, ресурсам и арифметике, роли/полномочиям, "
                 "согласованности публичной задачи и закрытых целей, ограничениям/условиям уступки, неизвестному, "
                 "публичным свидетелям и возможности содержательной игры на шесть ходов. Найди причинные противоречия и "
                 "объективно недостижимые уступки. Не раскрывай частные факты/мотивы и не копируй исходные значения закрытых полей. "
                 "В summary дай для КАЖДОГО alias G01...G12 краткий вердикт PASS/WARN/FAIL и тип проблемы, без пересказа кейса; "
                 "не более 1500 символов всего. strengths=[] и risks=[] (цитат игрока здесь нет), next_step — общий "
                 "проверяемый критерий приёмки (до 1000 символов), example_phrase=null. Не выдавай красивую прозу за доказательство.\n" +
                 "Методология:\n" + RUNTIME_SPEC + "\nКейсы:\n" + json.dumps(aliases, ensure_ascii=False)}]
    result, meta = await runner.call(MODELS[0], "judge", "negotiation_only", messages,
        {"case": {}, "history": []}, label="independent-blind-generator-audit-12", style="semantic-audit",
        selected={"max_tokens": 3500, "effort": "medium", "temperature": .3})
    if result["parsed"] and any(_hidden_leak(v, row["case"]) for v in _all_strings(result["parsed"]) for row in candidates):
        runner.budget.complete(meta["id"], {"status": "validation_failed", "validation_error": "audit private-context overlap"})
        result["parsed"] = None
    print(json.dumps({"id": meta["id"], "cost_usd": meta["cost_usd"], "report": result["parsed"]}, ensure_ascii=False))
    (PRIVATE / "generator-audit-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", required=True)
    p.parse_args()
    asyncio.run(run())
