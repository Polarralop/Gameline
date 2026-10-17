#!/bin/sh
# Build Gameline.app into dist/.
#   ./build_app.sh          full, standalone build (for the demo)
#   ./build_app.sh --alias  alias build that runs this source folder (for day-to-day use)
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
.venv/bin/pip install -q py2app
# Move any old repo-local data into ~/Library/Application Support/Gameline first,
# so the app sees the same deadlines as ./run.sh.
.venv/bin/python -c "from gameline.paths import migrate_legacy_data as m; [print('Moved', p) for p in m()]"
# The repo's .env is the one you edit; the full app can only read the copy in
# the data folder, so refresh that copy on every build.
if [ -f .env ]; then
  cp .env "$HOME/Library/Application Support/Gameline/.env"
fi
.venv/bin/python packaging/make_icon.py  # compiles packaging/AppIcon.icon (needs Xcode)
rm -rf build dist
if [ "$1" = "--alias" ]; then
  .venv/bin/python setup.py -q py2app -A
else
  .venv/bin/python setup.py -q py2app
  .venv/bin/python packaging/prune_qt.py dist/Gameline.app
  # google-genai lives in the `google` namespace package, which py2app can't
  # trace; copy it next to the other bundled packages.
  cp -R .venv/lib/python3*/site-packages/google dist/Gameline.app/Contents/Resources/lib/python3*/
  codesign --force --deep --sign - dist/Gameline.app  # re-sign after trimming (ad-hoc)
fi
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
if [ "$1" = "--alias" ]; then
  # Alias builds run this source folder, so they stay in dist/.
  touch dist/Gameline.app
  "$LSREGISTER" -f dist/Gameline.app || true
  echo "Built dist/Gameline.app (alias). Open it with: open dist/Gameline.app"
else
  # Install outside ~/Documents: macOS asks for Documents access whenever an
  # app stored there reads its own files.
  osascript -e 'quit app "Gameline"' >/dev/null 2>&1 || true
  pkill -f "Gameline.app/Contents/MacOS/Gameline" >/dev/null 2>&1 || true
  rm -rf /Applications/Gameline.app
  ditto dist/Gameline.app /Applications/Gameline.app
  rm -rf dist/Gameline.app  # one copy, so Spotlight and the Dock don't find two
  touch /Applications/Gameline.app
  "$LSREGISTER" -f /Applications/Gameline.app || true
  echo "Installed /Applications/Gameline.app. Open it with: open -a Gameline"
fi
