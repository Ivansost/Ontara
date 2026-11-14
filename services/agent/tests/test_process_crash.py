import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def test_real_sigkill_then_fresh_process_reconciles_one_external_effect(tmp_path):
    environment = dict(os.environ, ONTARA_PROCESS_TEST_ROOT=str(tmp_path), ONTARA_ENABLE_DEMO_FAULTS="1")
    fixture = Path(__file__).with_name("process_fixture.py")
    first = subprocess.run([sys.executable, str(fixture)], env=environment, timeout=20, capture_output=True)
    assert first.returncode == -signal.SIGKILL
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["state"] == "dispatch_started" and "receipt" not in ledger
    receiver = json.loads((tmp_path / "receiver.json").read_text())
    assert receiver["ticketCount"] == receiver["createRequestCount"] == 1
    second = subprocess.run([sys.executable, str(fixture)], env=environment, timeout=20, capture_output=True)
    assert second.returncode == 0, second.stderr.decode()
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["state"] == "receipt_verified"
    assert json.loads((tmp_path / "receiver.json").read_text())["createRequestCount"] == 1
    starts = [e for e in json.loads((tmp_path / "events.json").read_text()) if e["kind"] == "execution_process_started"]
    assert len(starts) == 2
    assert len({e["data"]["processId"] for e in starts}) == 2
    assert len({e["attemptId"] for e in starts}) == 2
