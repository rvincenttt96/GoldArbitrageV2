from pathlib import Path
import re

p = Path("./config/settings.py")
s = p.read_text(encoding="utf-8")

s, n = re.subn(
    r'(?m)^GOLDIKA_BUY_ENABLED\s*=\s*.*$',
    'GOLDIKA_BUY_ENABLED = True',
    s
)

if n != 1:
    raise Exception(
        f"GOLDIKA_BUY_ENABLED replacements: {n}"
    )

p.write_text(
    s,
    encoding="utf-8"
)

print("GOLDIKA BUY ENABLED")
