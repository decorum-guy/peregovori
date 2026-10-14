"""Zero-GPU regression checks for the upcoming course-methodology ablation."""
import copy
import json
import unittest
from pathlib import Path

from evaluation.methodology_context import (
    VERSION, _catalog, augmented_messages, build_addendum,
    identity_manifest, selected_techniques,
)
from evaluation.run_methodology_abc_and_stop import candidate_for


ROOT=Path(__file__).resolve().parents[2]
EXAMPLE=json.loads((ROOT/"examples/case.example.json").read_text(encoding="utf-8"))


class MethodologyAblationTests(unittest.TestCase):
    def setUp(self):
        self.case=copy.deepcopy(EXAMPLE)
        self.dialogue=[
            {"role":"assistant","content":self.case["opponent"]["opening"]},
            {"role":"user","content":"Есть конкретный расчёт нагрузки или пока это опасение?"},
        ]

    def test_14b_epoch1_is_default_candidate_path(self):
        c = candidate_for("14b-e1")
        self.assertEqual(c.model, "Qwen/Qwen3-14B")
        self.assertEqual(c.epoch, 1)
        self.assertEqual(c.baseline.name, "qwen3_14b_e1")
        self.assertEqual(c.adapter.name, "adapter_epoch_1")
        self.assertEqual(c.review.name, "methodology_abc_14b_e1_review")
        self.assertIn("14b-e1", c.tag)
        c2 = candidate_for("14b-e2")
        self.assertEqual(c2.model, c.model)
        self.assertEqual(c2.adapter.name, "adapter_epoch_2")
        self.assertNotEqual(c2.review, c.review)
        old = candidate_for("8b-e2")
        self.assertEqual(old.model, "Qwen/Qwen3-8B")
        self.assertEqual(old.baseline.name, "qwen3_8b_e2")

    def test_a_is_completely_unchanged(self):
        original=[{"role":"system","content":"ORIGINAL SYSTEM PROMPT"},*self.dialogue]
        modified,ids=augmented_messages(original,self.case,"A")
        self.assertIs(modified,original)
        self.assertEqual(ids,[])
        self.assertEqual(original[0]["content"],"ORIGINAL SYSTEM PROMPT")

    def test_generic_b_contains_course_rules_but_no_technique_list(self):
        addition,ids=build_addendum(self.case,self.dialogue,"B")
        self.assertEqual(ids,[])
        self.assertIn("МЕТОДОЛОГИЧЕСКИЕ ПРАВИЛА",addition)
        self.assertIn("Тема на переговоры",addition)
        self.assertNotIn("ПРИМЕРЫ РЕЛЕВАНТНЫХ",addition)

    def test_c_contains_exactly_ten_distinct_real_course_techniques(self):
        addition,ids=build_addendum(self.case,self.dialogue,"C")
        self.assertEqual(len(ids),10)
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(x in _catalog() for x in ids))
        self.assertIn("ОНИ НЕ ОГРАНИЧИВАЮТ ТВОЙ РЕПЕРТУАР",addition)
        self.assertIn("ЛЮБЫЕ другие уместные способы",addition)
        self.assertLess(len(addition),9500)

    def test_never_uses_hidden_teaching_or_oracle_for_selection(self):
        first=selected_techniques(self.case,self.dialogue)
        self.case["teaching"]={"focus_techniques":["SECRET_CORRECT_MOVE"],"oracle":"HIDDEN"}
        self.case["oracle"]={"must":["SECRET_CORRECT_MOVE"]}
        self.case["private_gold_answer"]="SECRET_CORRECT_MOVE"
        second=selected_techniques(self.case,self.dialogue)
        self.assertEqual(first,second)
        addition,_=build_addendum(self.case,self.dialogue,"C")
        self.assertNotIn("SECRET_CORRECT_MOVE",addition)

    def test_every_role_and_scenario_selects_exactly_ten(self):
        for role in ("MODEL_MANIPULATOR","MODEL_DEFENDER","MODEL_NEGOTIATOR"):
            for scenario in ("negotiation_only","conflict_only","conflict_then_negotiation",
                             "unintentional_boundary","stage4"):
                with self.subTest(role=role,scenario=scenario):
                    case=copy.deepcopy(self.case)
                    case["category"]=role
                    case["scenario"]=scenario
                    ids=[t["id"] for t in selected_techniques(case,self.dialogue)]
                    self.assertEqual(len(ids),10)
                    self.assertEqual(len(set(ids)),10)

    def test_selection_is_deterministic_and_yaml_fingerprinted(self):
        one=selected_techniques(self.case,self.dialogue)
        two=selected_techniques(self.case,self.dialogue)
        self.assertEqual(one,two)
        manifest=identity_manifest()
        self.assertEqual(manifest["version"],VERSION)
        self.assertEqual(manifest["techniques_per_probe"],10)
        self.assertEqual(len(manifest["course_files_sha256"]["techniques"]),64)

    def test_b_c_do_not_modify_history(self):
        original=[{"role":"system","content":"ROLE CARD"},*self.dialogue]
        for v in ("B","C"):
            newer,_=augmented_messages(original,self.case,v)
            self.assertEqual(newer[1:],original[1:])
            self.assertEqual(original[0]["content"],"ROLE CARD")
            self.assertIsNot(newer[0],original[0])


if __name__=="__main__":
    unittest.main()
