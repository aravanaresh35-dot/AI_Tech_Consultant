#!/usr/bin/env python3
"""Build dist/ai-tech-consultant.zip from git-tracked + untracked-but-not-ignored files, plus .git history.
Excludes anything gitignored (.env, venvs, node_modules, caches, sqlite files, logs) and refuses to ship real-looking secrets."""
import re, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
files = sorted({f for f in files if f and (ROOT / f).is_file()})
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|ANTHROPIC_API_KEY\s*=\s*[A-Za-z0-9_-]{15,}")
bad = [f for f in files if f.endswith(".env") or Path(f).name == ".env" or SECRET.search((ROOT / f).read_text(errors="ignore"))]
if bad:
    sys.exit(f"Refusing to zip, possible secrets in: {bad}")
out = ROOT / "dist" / "ai-tech-consultant.zip"
out.parent.mkdir(exist_ok=True)
if out.exists():
    out.unlink()
n = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(ROOT / f, f"ai-tech-consultant/{f}"); n += 1
    for p in sorted((ROOT / ".git").rglob("*")):
        if p.is_file():
            z.write(p, f"ai-tech-consultant/{p.relative_to(ROOT)}"); n += 1
print(f"wrote {out} ({out.stat().st_size} bytes, {n} entries)")
