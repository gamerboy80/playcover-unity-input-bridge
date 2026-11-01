#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
mkdir -p build
xcrun clang -Wall -Wextra -Werror tests/scroll.c -o build/test-scroll
build/test-scroll
xcrun clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit tests/native-wheel.m -o build/test-native-wheel
build/test-native-wheel
