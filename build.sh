#!/bin/sh
set -eu
cd "$(dirname "$0")"
sdk=$(xcrun --sdk macosx --show-sdk-path)
profile=${1:-zzz-3.3.0}
# Validate before using the ID as a path component.
python3 -c 'import sys; from profiles import load_profile; load_profile(sys.argv[1])' "$profile"
build_dir="build/$profile"
mkdir -p "$build_dir"
python3 profiles.py "$profile" "$build_dir/Profile.h"
xcrun clang -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
  -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
  -F"$sdk/System/iOSSupport/System/Library/Frameworks" \
  -L"$sdk/System/iOSSupport/usr/lib" \
  -I"$build_dir" -dynamiclib -fobjc-arc -Wall -Wextra -Werror \
  -framework Foundation -framework UIKit \
  -install_name @executable_path/Frameworks/NativeInputBridge.dylib \
  src/NativeInputBridge.m -o "$build_dir/NativeInputBridge.dylib"
codesign --force --sign - "$build_dir/NativeInputBridge.dylib"
codesign --verify --strict "$build_dir/NativeInputBridge.dylib"
