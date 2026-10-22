"""Smoke test: the Streamlit app starts headless and its health endpoint answers ok.

Starts a real `streamlit run ui/app.py` subprocess on a free port (no browser,
no usage stats) and stops only that process. The API doesn't need to run.
"""

import os
import socket
import subprocess
import sys
import time
import unittest

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
START_TIMEOUT_SECONDS = 60


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StreamlitSmokeTest(unittest.TestCase):
    def test_app_starts_headless(self):
        port = free_port()
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", os.path.join("ui", "app.py"),
             "--server.headless", "true", "--server.port", str(port), "--server.address", "127.0.0.1",
             "--browser.gatherUsageStats", "false"],
            cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + START_TIMEOUT_SECONDS
            health = None
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    health = httpx.get("http://127.0.0.1:{0}/_stcore/health".format(port), timeout=2)
                    break
                except httpx.TransportError:
                    time.sleep(0.5)
            self.assertIsNone(process.poll(), "streamlit exited early with code {0}".format(process.returncode))
            self.assertIsNotNone(health, "no health answer within {0} s".format(START_TIMEOUT_SECONDS))
            self.assertEqual((health.status_code, health.text), (200, "ok"))
        finally:
            process.terminate()
            try:
                process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    unittest.main()
