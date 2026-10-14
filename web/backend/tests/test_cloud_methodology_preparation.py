import pytest
from app.cloud_methodology import methodology_messages, TECHNIQUE_IDS
from app.prompts import roleplay_messages
from app.spoken_dialogue import spoken_roleplay_messages
from app.providers import _mock_case


@pytest.mark.parametrize("scenario", list(TECHNIQUE_IDS))
@pytest.mark.parametrize("language", ["ru", "en"])
def test_exact_a_isolation_and_nonexclusive_ten_techniques(scenario, language):
    case = _mock_case({"scenario": scenario, "language": language})
    history = [{"speaker": "opponent", "text": case["opponent"]["opening"]}, {"speaker": "player", "text": "Player move"}]
    assert methodology_messages(case, history, language, spoken=False) == roleplay_messages(case, history, language)
    assert methodology_messages(case, history, language) == spoken_roleplay_messages(case, history, language)
    b = methodology_messages(case, history, language, variant="B")
    c = methodology_messages(case, history, language, variant="C")
    assert c[1:] == b[1:] == roleplay_messages(case, history, language)[1:]
    assert len(set(TECHNIQUE_IDS[scenario])) == 10
    assert sum(c[0]["content"].count("- id: " + key + "\n") for key in TECHNIQUE_IDS[scenario]) == 10
    assert ("ЛЮБЫЕ" if language == "ru" else "ANY") in c[0]["content"]
    assert '"teaching":' not in c[0]["content"]


def test_invalid_variant_rejected():
    with pytest.raises(ValueError):
        methodology_messages({}, [], variant="D")
