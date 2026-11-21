#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
sdk=$(xcrun --sdk macosx --show-sdk-path)
output=build/plugins/ZZZDamageProbe.dylib
python3 plugins/zzz_damage/stage.py --header build/plugins/ZZZDamageProfile.h
xcrun clang -I build/plugins -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
    -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
    -dynamiclib -fobjc-arc -Wall -Wextra -Werror -framework Foundation -framework UIKit \
    -install_name @rpath/ZZZDamageProbe.dylib \
    plugins/zzz_damage/ZZZDamageProbe.m -o "$output"
codesign --force --sign - "$output"
codesign --verify --strict "$output"
printf 'Built %s/%s\n' "$PWD" "$output"
