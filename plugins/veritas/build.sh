#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
sdk=$(xcrun --sdk macosx --show-sdk-path)
output=build/plugins/VeritasLive.dylib
mkdir -p "$(dirname "$output")"
python3 plugins/veritas/stage.py --header build/plugins/VeritasProfile.h
xcrun clang -I build/plugins -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
  -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
  -dynamiclib -fobjc-arc -Wall -Wextra -Werror \
  -framework Foundation -framework CoreGraphics -framework UIKit \
  -install_name @rpath/VeritasLive.dylib \
  plugins/veritas/VeritasLive.m -o "$output"
codesign --force --sign - "$output"
codesign --verify --strict "$output"
printf 'Built %s/%s\n' "$PWD" "$output"
