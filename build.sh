#!/bin/sh
set -eu

step='starting the build'
on_error() {
  result=$?
  trap - EXIT
  if [ "$result" -ne 0 ]; then
    printf 'Build stopped while %s (exit status %s).\n' "$step" "$result" >&2
  fi
  exit "$result"
}
trap on_error EXIT

cd "$(dirname "$0")"
profile=${1:-zzz-3.3.0}
printf 'Preparing the input bridge for profile %s...\n' "$profile"

step='finding the macOS build tools'
sdk=$(xcrun --sdk macosx --show-sdk-path)

# Validate before using the ID as a path component.
step='checking the selected game profile'
profile=$(python3 -c 'import sys; from profiles import load_profile; print(load_profile(sys.argv[1])["id"])' "$profile")
printf 'Using profile %s.\n' "$profile"

build_dir="build/$profile"
mkdir -p "$build_dir"

step='generating the profile settings'
printf 'Preparing profile settings...\n'
python3 profiles.py "$profile" "$build_dir/Profile.h"

step='compiling the input bridge'
printf 'Compiling the input bridge...\n'
xcrun clang -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
  -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
  -F"$sdk/System/iOSSupport/System/Library/Frameworks" \
  -L"$sdk/System/iOSSupport/usr/lib" \
  -I"$build_dir" -dynamiclib -fobjc-arc -Wall -Wextra -Werror \
  -framework Foundation -framework UIKit -framework CoreGraphics \
  -install_name @executable_path/Frameworks/NativeInputBridge.dylib \
  src/NativeInputBridge.m -o "$build_dir/NativeInputBridge.dylib"

step='signing and verifying the input bridge'
printf 'Signing and checking the build...\n'
codesign --force --sign - "$build_dir/NativeInputBridge.dylib"
codesign --verify --strict "$build_dir/NativeInputBridge.dylib"
printf 'Build complete: %s/NativeInputBridge.dylib\n' "$build_dir"
