#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
mkdir -p build/plugins
python3 plugins/veritas/stage.py --header build/plugins/VeritasProfile.h
sdk=$(xcrun --sdk macosx --show-sdk-path)
xcrun clang++ -I plugins/veritas -I build/plugins -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
    -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
    -F"$sdk/System/iOSSupport/System/Library/Frameworks" -L"$sdk/System/iOSSupport/usr/lib" \
    -fobjc-arc -Wall -Wextra -Werror -framework UIKit -framework Foundation -framework CoreGraphics \
    plugins/veritas/preview.m plugins/veritas/Assets.mm -o build/veritas-preview
build/veritas-preview
printf 'Rendered build/plugins/VeritasPreview.png (synthetic data)\n'
