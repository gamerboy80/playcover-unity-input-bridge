#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
mkdir -p build
xcrun clang -fobjc-arc -Wall -Wextra -Werror -framework Foundation tests/pointer-lock.m -o build/test-pointer-lock
build/test-pointer-lock
sdk=$(xcrun --sdk macosx --show-sdk-path)
xcrun clang -target arm64-apple-ios15.0-macabi -isysroot "$sdk" \
    -iframework "$sdk/System/iOSSupport/System/Library/Frameworks" \
    -F"$sdk/System/iOSSupport/System/Library/Frameworks" \
    -L"$sdk/System/iOSSupport/usr/lib" -fobjc-arc -Wall -Wextra -Werror \
    -framework Foundation -framework UIKit tests/text-input.m -o build/test-text-input
build/test-text-input
python3 plugins/zzz_damage/stage.py --header build/plugins/ZZZDamageProfile.h
xcrun clang -I build/plugins -I plugins/zzz_damage -Wall -Wextra -Werror \
    plugins/zzz_damage/test-probe.c -o build/test-zzz-damage
build/test-zzz-damage
xcrun clang -I plugins/zzz_damage -fobjc-arc -Wall -Wextra -Werror -framework Foundation \
    plugins/zzz_damage/test-dashboard.m -o build/test-zzz-dashboard
build/test-zzz-dashboard
python3 plugins/veritas/stage.py --header build/plugins/VeritasProfile.h
xcrun clang -I plugins/veritas -fobjc-arc -Wall -Wextra -Werror -framework Foundation \
    plugins/veritas/test-live.m -o build/test-veritas
build/test-veritas
xcrun clang -I plugins/veritas -fobjc-arc -Wall -Wextra -Werror -framework Foundation \
    plugins/veritas/test-server.m -o build/test-veritas-server
build/test-veritas-server
sh plugins/veritas/test-assets.sh
xcrun clang -Wall -Wextra -Werror tests/scroll.c -o build/test-scroll
build/test-scroll
xcrun clang -Wall -Wextra -Werror tests/mouse-presence.c -o build/test-mouse-presence
build/test-mouse-presence
for typed in 0 1; do
    xcrun clang -Wall -Wextra -Werror -DGameTypeStatics=$typed \
        tests/input-statics.c -o build/test-input-statics-$typed
    build/test-input-statics-$typed
done
for buttons in 0 1; do
    xcrun clang -fobjc-arc -Wall -Wextra -Werror -framework Foundation \
        -DGameLegacyButtons=$buttons tests/legacy-backend.m -o build/test-legacy-$buttons
    build/test-legacy-$buttons
done
xcrun clang -fobjc-arc -Wall -Wextra -Werror -framework AppKit tests/native-wheel.m -o build/test-native-wheel
build/test-native-wheel
for backend in 0 1; do
    xcrun clang -I build/plugins -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
        -DGameLegacyBackend=$backend tests/event-handler.m -o build/test-event-handler-$backend
    build/test-event-handler-$backend
done
xcrun clang -I build/plugins -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
    -DGameNativeMenuButtons=1 tests/event-handler.m -o build/test-event-handler-native-menu
build/test-event-handler-native-menu
xcrun clang -I build/plugins -fobjc-arc -Wall -Wextra -Werror -framework AppKit \
    -DGameLegacySupplement=1 -DGameNativeMenuButtons=1 tests/event-handler.m -o build/test-event-handler-supplement
build/test-event-handler-supplement
