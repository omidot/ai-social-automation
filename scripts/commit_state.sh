#!/usr/bin/env bash
set -euo pipefail
git config user.name "ai-social-bot"
git config user.email "bot@users.noreply.github.com"

# Stage each state path independently. A single `git add a b c` fails the WHOLE
# command (staging nothing) if any pathspec matches no files — which is exactly
# what happened when `output/` stopped existing. Add only paths that exist.
for p in data assets; do
  [ -e "$p" ] && git add "$p" || true
done

echo "--- staged ---"
git diff --cached --name-only || true
echo "--------------"

if git diff --cached --quiet; then
  echo "no state changes"
  exit 0
fi
git commit -m "chore(state): update pipeline state [skip ci]"
for i in 1 2 3; do
  if git pull --rebase --autostash && git push; then
    echo "pushed"; exit 0
  fi
  echo "push retry $i"; sleep 5
done
echo "failed to push state" >&2
exit 1
