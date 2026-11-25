#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
mkdir -p build/plugins
python3 plugins/veritas/stage.py --header build/plugins/VeritasProfile.h
sdk=$(xcrun --sdk macosx --show-sdk-path)
xcrun clang++ -I plugins/veritas -I build/plugins -include plugins/veritas/test-assets-profile.h \
    -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
    -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
    -F"$sdk/System/iOSSupport/System/Library/Frameworks" -L"$sdk/System/iOSSupport/usr/lib" \
    -fobjc-arc -Wall -Wextra -Werror -framework UIKit -framework Foundation \
    plugins/veritas/test-assets.mm plugins/veritas/Assets.mm -o build/test-veritas-assets
build/test-veritas-assets
