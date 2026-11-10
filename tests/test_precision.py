import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "precision.py"


def run(tmp_path, rows):
    f = tmp_path / "s.csv"
    f.write_text("listing_id,url,text,verdict,stage,label\n" + "\n".join(rows) + "\n")
    return subprocess.run([sys.executable, str(SCRIPT), str(f)], capture_output=True, text=True)


def test_precision(tmp_path):
    r = run(tmp_path, ["1,u,t,pass,rules,owner", "2,u,t,pass,rules,owner", "3,u,t,pass,llm,owner",
                       "4,u,t,pass,llm,broker"])
    assert r.returncode == 0 and r.stdout.strip() == "precision=0.75 (3/4)"


def test_unlabelled_fails(tmp_path):
    r = run(tmp_path, ["1,u,t,pass,rules,owner", "2,u,t,pass,rules,"])
    assert r.returncode == 1 and "unlabelled" in r.stderr
