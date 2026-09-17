#!/usr/bin/env bash
# Publish this repo to a Hugging Face Space (Docker SDK).
#
#   deploy/space_sync.sh <hf-username>/<space-name>
#
# It sends everything git tracks, plus two things git ignores on purpose:
#   - data/  the seeded catalog (SQLite + Chroma + product photos, ~12 MB); the Space has no
#            Pexels/Gemini keys to re-run scripts/seed_catalog.py with
#   - README.md  replaced by deploy/space/README.md, which carries the Space's YAML header
#
# API keys are NOT sent. Add GROQ_API_KEY and GOOGLE_API_KEY as secrets in the Space's
# Settings -> Variables and secrets page.
set -euo pipefail

SPACE=${1:-}
[ -n "$SPACE" ] || { echo "usage: deploy/space_sync.sh <hf-username>/<space-name>" >&2; exit 1; }

ROOT=$(git rev-parse --show-toplevel)
[ -f "$ROOT/data/giftvoice.db" ] || { echo "data/ is not seeded - run scripts/seed_catalog.py first" >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

git clone "https://huggingface.co/spaces/$SPACE" "$WORK/space"
cd "$WORK/space"
# Keep .git, replace everything else with the current commit.
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
git -C "$ROOT" archive HEAD | tar -x -C "$WORK/space"
cp -r "$ROOT/data" "$WORK/space/data"
cp "$ROOT/deploy/space/README.md" "$WORK/space/README.md"

# -f because the repo's .gitignore excludes data/, which the Space needs.
git add -A -f .
git commit -m "Deploy GiftVoice $(git -C "$ROOT" rev-parse --short HEAD)" || { echo "Nothing changed."; exit 0; }
git push
echo "Pushed. The Space rebuilds automatically: https://huggingface.co/spaces/$SPACE"
