import os
import subprocess
import sys
from pathlib import Path


def test_smoke_mcp_script() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    proc = subprocess.run(
        [sys.executable, str(root / "tests" / "smoke_mcp.py")],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "✅ initialize" in proc.stdout
    assert "✅ tools/list: 7 tools" in proc.stdout
    assert "invalid_token" in proc.stdout
