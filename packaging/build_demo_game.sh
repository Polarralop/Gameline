#!/bin/sh
# Prebuild the demo "game" (a process that just sleeps) as a universal binary,
# so users of Gameline.app don't need Xcode's command-line tools.
set -e
dir="$(cd "$(dirname "$0")" && pwd)/icon-build"
mkdir -p "$dir"
printf '#include <unistd.h>\nint main(void){for(;;)pause();}\n' > "$dir/demo_game.c"
/usr/bin/cc -arch arm64 -arch x86_64 -O2 -o "$dir/GamelineDemoGame" "$dir/demo_game.c"
echo "$dir/GamelineDemoGame"
