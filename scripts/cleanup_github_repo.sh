#!/usr/bin/env bash
#
# Removes files that should never have been committed to GoldArbitrageV2.
#
# Touches only the working tree and creates one ordinary commit. It does NOT
# rewrite history and does NOT remove credentials, because both were explicitly
# out of scope. Anything already in the history stays there.
#
#   git clone https://github.com/rvincenttt96/GoldArbitrageV2.git
#   cd GoldArbitrageV2
#   bash cleanup_github_repo.sh          # shows what would go
#   bash cleanup_github_repo.sh --apply  # actually removes it
#   git push

set -euo pipefail

APPLY=false
[ "${1:-}" = "--apply" ] && APPLY=true

git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repository"; exit 1; }

# Each pattern is one category of accumulated debris. Kept explicit rather than
# clever so that anything unexpected is easy to spot before it is deleted.
PATTERNS=(
  # Vendored dependencies. 3,200-odd files that npm install recreates.
  'telegram-proxy/*/node_modules/*'
  'telegram-proxy/node_modules/*'
  '*/node_modules/*'
  'node_modules/*'

  # Local tool state, never meaningful to another machine.
  '.wrangler/*'
  '*/.wrangler/*'
  '__pycache__/*'
  '*/__pycache__/*'
  '*.pyc'

  # Editor-style backups. Version control already does this job.
  '*_backup*.py'
  '*_backup*.py.*'
  '*.bak'
  '*.bak_*'
  '*.py.bak*'
  '*backup_before*'
  'live_bot_backup*'

  # One-off scripts that rewrote source files with regex at runtime. These stood
  # in for version control and are actively misleading to keep.
  'patch_*.py'

  # Throwaway probes against the live APIs, already listed in .gitignore.
  'debug_*.py'
  'discover_*.py'
  'inspect_*.py'
  'probe_*.py'
  'enable_goldika_buy.py'
  'fix_wallgold_sell_rate.py'
  'audit_after_execution_error.py'

  # Scratch output.
  '*.log'
  'result.txt'
  'sell_fix.txt'
  'sell_method.txt'
  'login_fix.txt'
  'goldika_wallet_discovery.txt'

  # A megabyte of captured site bundle, kept as a reference by hand.
  'milli.js'
)

echo "Scanning for files to remove..."
MATCHES=$(mktemp)
for pattern in "${PATTERNS[@]}"; do
  git ls-files -z -- "$pattern" 2>/dev/null | tr '\0' '\n' >> "$MATCHES" || true
done
sort -u "$MATCHES" -o "$MATCHES"

COUNT=$(grep -c . "$MATCHES" || true)
if [ "$COUNT" -eq 0 ]; then
  echo "Nothing to remove."
  rm -f "$MATCHES"
  exit 0
fi

echo
echo "By category:"
for label in node_modules .wrangler __pycache__ backup .bak patch_ debug_ .log .pyc; do
  n=$(grep -c -- "$label" "$MATCHES" || true)
  [ "$n" -gt 0 ] && printf "  %-14s %6s\n" "$label" "$n"
done
echo
printf "  %-14s %6s\n" "TOTAL" "$COUNT"
echo
echo "Sample:"
head -15 "$MATCHES" | sed 's/^/  /'
[ "$COUNT" -gt 15 ] && echo "  ... and $((COUNT - 15)) more"

if [ "$APPLY" != true ]; then
  echo
  echo "Dry run. Re-run with --apply to remove these."
  rm -f "$MATCHES"
  exit 0
fi

echo
echo "Removing..."
# --cached would leave them on disk and out of git; a plain rm is what is wanted
# here, since none of these are worth keeping locally either.
xargs -a "$MATCHES" -d '\n' git rm -r --quiet --ignore-unmatch --
rm -f "$MATCHES"

cat > .gitignore <<'IGNORE'
__pycache__/
*.py[cod]
*.log

.venv/
venv/
node_modules/
.wrangler/

.env
*.har

# Backups belong in git history, not next to the file they shadow.
*.bak
*.bak_*
*_backup*.py
*backup_before*
IGNORE

git add .gitignore
git commit -q -m "Remove vendored dependencies, backups and scratch files

Drops node_modules, .wrangler state, __pycache__, ad-hoc backup copies, the
patch_*.py scripts that rewrote source with regex at runtime, and assorted
scratch output. Tightens .gitignore so they stay out.

History is untouched: this only stops the working tree carrying them."

echo
echo "Done. Review with 'git show --stat HEAD', then 'git push'."
