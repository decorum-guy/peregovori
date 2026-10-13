import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from inference.config import QwenSettings, validate_adapter
from inference.preflight import memory_estimate, validate_shapes
from inference.runtime import InferenceError, character_answer, fit_messages
from inference.server import create_app


def adapter(tmp_path, base='Qwen/Qwen3-8B'):
    (tmp_path / 'adapter_config.json').write_text(json.dumps({'base_model_name_or_path': base, 'peft_type': 'LORA', 'task_type': 'CAUSAL_LM'}))
    (tmp_path / 'adapter_model.safetensors').write_bytes(b'fixture-only-not-real-weights')
    return tmp_path


@pytest.mark.parametrize('base', ['Qwen/Qwen3-8B', 'Qwen/Qwen3-14B'])
def test_8b_and_14b_configuration_needs_matching_adapter(tmp_path, base):
    settings = QwenSettings(base_model=base, adapter_path=adapter(tmp_path, base))
    validate_adapter(settings)
    other = QwenSettings(base_model='Qwen/Qwen3-14B' if base.endswith('8B') else 'Qwen/Qwen3-8B', adapter_path=tmp_path)
    with pytest.raises(ValueError, match='8B'):
        validate_adapter(other)


def test_adapter_weights_are_required(tmp_path):
    settings = QwenSettings(adapter_path=adapter(tmp_path))
    (tmp_path / 'adapter_model.safetensors').unlink()
    with pytest.raises(ValueError, match='safetensors'):
        validate_adapter(settings)


def test_tensor_shapes_cannot_hide_an_8b_adapter_in_14b_metadata():
    config = SimpleNamespace(hidden_size=5120, head_dim=128, num_attention_heads=40, num_key_value_heads=8, intermediate_size=17408)
    shapes = {'model.layers.0.self_attn.q_proj.lora_A.weight': [16, 4096], 'model.layers.0.self_attn.q_proj.lora_B.weight': [4096, 16]}
    with pytest.raises(ValueError, match='совместимы'):
        validate_shapes(shapes, config)
    good = {key: ([32, 5120] if '.lora_A.' in key else [5120, 32]) for key in shapes}
    validate_shapes(good, config)
    config.num_hidden_layers, config.vocab_size, config.tie_word_embeddings = 40, 151936, False
    low, high = memory_estimate(config, QwenSettings(base_model='Qwen/Qwen3-14B'), 100 * 2**20)
    assert 13 < low < high < 24


@pytest.mark.parametrize('text', ['<think>private unfinished thought', 'secret</think>', '<think>secret</think>'])
def test_unfinished_or_empty_thinking_is_never_returned(text):
    with pytest.raises(InferenceError):
        character_answer(text)


def test_complete_thinking_block_is_removed():
    assert character_answer('<think>private thought</think>Я готов обсудить сроки.') == 'Я готов обсудить сроки.'


def test_context_shortening_keeps_system_opening_last_turn_and_non_thinking():
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs['enable_thinking'] is False
            self.last = messages
            return SimpleNamespace(shape=[1, len(messages) * 100])
    tokenizer = Tokenizer()
    messages = [{'role': 'system', 'content': 'character'}, {'role': 'assistant', 'content': 'opening'},
                {'role': 'user', 'content': 'old'}, {'role': 'assistant', 'content': 'old reply'}, {'role': 'user', 'content': 'last'}]
    fit_messages(messages, tokenizer, 300)
    assert [m['content'] for m in tokenizer.last] == ['character', 'opening', 'last']
    with pytest.raises(InferenceError):
        fit_messages(messages, tokenizer, 200)


class FakeRuntime:
    def __init__(self, fail=False):
        self.ready = False
        self.fingerprint = 'a' * 64
        self.release = threading.Event()
        self.fail = fail
    def load(self):
        self.release.wait(timeout=3)
        if self.fail:
            raise RuntimeError('SECRET_SENTINEL_LOAD')
        self.ready = True
    def generate(self, messages, max_tokens, temperature):
        assert messages[0]['role'] == 'system' and messages[-1]['role'] == 'user'
        return 'Я готов обсудить условия.', 100, 8


def wait_status(client, status):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        health = client.get('/health').json()
        if health['status'] == status:
            return health
        time.sleep(0.01)
    raise AssertionError('load did not finish')


def test_api_is_not_ready_until_base_and_adapter_load_and_warmup_complete():
    runtime = FakeRuntime()
    with TestClient(create_app(QwenSettings(), runtime)) as client:
        payload = {'model': 'qwen3-custom', 'messages': [{'role': 'system', 'content': 'Персонаж'}, {'role': 'user', 'content': 'Привет'}]}
        health = client.get('/health').json()
        assert health['status'] == 'loading' and not health['ready'] and not health['adapter_loaded']
        assert client.post('/v1/chat/completions', json=payload).status_code == 503
        runtime.release.set()
        health = wait_status(client, 'ready')
        assert health['ready'] and health['adapter_loaded'] and health['base_model'] == 'Qwen/Qwen3-8B'
        response = client.post('/v1/chat/completions', json=payload)
        assert response.status_code == 200
        assert response.json()['choices'][0]['message']['content'] == 'Я готов обсудить условия.'
        assert response.json()['usage']['total_tokens'] == 108
        assert client.post('/v1/chat/completions', json={**payload, 'model': 'different-checkpoint'}).status_code == 409
        assert client.post('/v1/chat/completions', json={**payload, 'adapter_fingerprint': 'b' * 64}).status_code == 409
        assert client.post('/v1/chat/completions', json={**payload, 'stream': True}).status_code == 400
        bad = client.post('/v1/chat/completions', json={**payload, 'messages': [{'role': 'invalid', 'content': 'PRIVATE_PROMPT_SENTINEL'}]})
        assert bad.status_code == 422 and 'PRIVATE_PROMPT_SENTINEL' not in bad.text


def test_failed_load_is_honestly_unavailable_without_exception_secrets(caplog):
    runtime = FakeRuntime(fail=True)
    runtime.release.set()
    with TestClient(create_app(QwenSettings(), runtime)) as client:
        health = wait_status(client, 'error')
    assert not health['ready'] and not health['adapter_loaded']
    assert 'SECRET_SENTINEL_LOAD' not in json.dumps(health) + caplog.text
