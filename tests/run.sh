#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
mkdir -p build
xcrun clang -Wall -Wextra -Werror tests/scroll.c -o build/test-scroll
build/test-scroll
xcrun clang -Wall -Wextra -Werror tests/mouse-presence.c -o build/test-mouse-presence
build/test-mouse-presence
xcrun clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit tests/native-wheel.m -o build/test-native-wheel
build/test-native-wheel
