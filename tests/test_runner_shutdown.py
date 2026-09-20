"""Real Ctrl+C with live SSE and a running pytest child, followed by same-port restart."""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process delivery uses the POSIX console contract")
def test_ctrl_c_releases_port_children_and_project_lock(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_wait.py").write_text("import time\ndef test_wait():\n    time.sleep(60)\n")
    env = {**os.environ, "CI": "1", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    processes = []
    streams = []

    def start(port, index):
        path = tmp_path / f"server-{index}.log"
        with path.open("w") as output:
            process = subprocess.Popen(
                [sys.executable, "-c", "from lounger.cli import main; main()", "runner", "--port", str(port)],
                cwd=tmp_path,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        processes.append(process)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            text = path.read_text()
            match = re.search(r"web runner → (http://[^\s\x1b]+)", text)
            if match:
                return process, match[1]
            assert process.poll() is None, text
            time.sleep(0.05)
        pytest.fail("Startup timeout: " + path.read_text())

    try:
        process, url = start(0, 1)
        with urlopen(url, timeout=5) as response:
            token = re.search(r'name="lounger-token" content="([^"]+)"', response.read().decode()).group(1)
        events = urlopen(url + "/api/v1/project/events", timeout=5)
        streams.append(events)
        assert events.readline().startswith(b"data:")
        payload = {
            "selection": {"nodeids": ["test_wait.py::test_wait"]},
            "options": {"verbosity": "normal", "html_report": False},
        }
        request = Request(
            url + "/api/v1/runs",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Lounger-Token": token},
        )
        with urlopen(request, timeout=10) as response:
            run = json.load(response)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with urlopen(url + "/api/v1/runs/" + run["id"], timeout=5) as response:
                run = json.load(response)
            if run.get("pid"):
                break
            time.sleep(0.05)
        assert run.get("pid"), run
        child_pid = run["pid"]
        logs = urlopen(url + "/api/v1/runs/" + run["id"] + "/events", timeout=5)
        streams.append(logs)
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=12) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        port = int(url.rsplit(":", 1)[1])
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        restarted, next_url = start(port, 2)
        assert next_url == url
        with urlopen(next_url + "/api/v1/project", timeout=5) as response:
            assert json.load(response)["busy"] is False
        restarted.send_signal(signal.SIGINT)
        assert restarted.wait(timeout=12) == 0
    finally:
        for stream in streams:
            stream.close()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
