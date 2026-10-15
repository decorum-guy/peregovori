from pathlib import Path
import pytest
from training.runtime_v2.check_adapter import check_adapter
from training.runtime_v2.common import file_inventory, write_json


@pytest.mark.parametrize("status", ["INCOMPLETE", "CUDA_BACKWARD_OPTIMIZER_PASS", "FAILED_OR_INTERRUPTED"])
def test_partial_or_preflight_never_final_candidate(tmp_path, status):
    write_json(tmp_path / "status.json", {"status": status})
    write_json(tmp_path / "identity.json", {})
    write_json(tmp_path / "SHA256.json", file_inventory(tmp_path))
    with pytest.raises(ValueError, match="not a candidate"):
        check_adapter(tmp_path)


def test_corrupt_result_sha_rejected_before_tensor_read(tmp_path):
    write_json(tmp_path / "status.json", {"status": "COMPLETE"})
    write_json(tmp_path / "SHA256.json", {"status.json": "0" * 64})
    with pytest.raises(ValueError, match="SHA"):
        check_adapter(tmp_path)
