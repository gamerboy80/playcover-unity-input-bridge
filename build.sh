#!/bin/sh
set -eu
cd "$(dirname "$0")"
sdk=$(xcrun --sdk macosx --show-sdk-path)
mkdir -p build
xcrun clang -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
  -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
  -F"$sdk/System/iOSSupport/System/Library/Frameworks" \
  -L"$sdk/System/iOSSupport/usr/lib" \
  -dynamiclib -fobjc-arc -Wall -Wextra -Werror \
  -framework Foundation -framework UIKit \
  -install_name @executable_path/Frameworks/NativeInputBridge.dylib \
  src/NativeInputBridge.m -o build/NativeInputBridge.dylib
codesign --force --sign - build/NativeInputBridge.dylib
codesign --verify --strict build/NativeInputBridge.dylib
