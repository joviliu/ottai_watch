#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 generate_project.py
if [ -n "${OTTAI_SIGN_IDENTITY:-}" ]; then
    xcodebuild -project OttaiMirror.xcodeproj -scheme OttaiMirror -configuration Release \
        -derivedDataPath build CODE_SIGN_IDENTITY="$OTTAI_SIGN_IDENTITY" CODE_SIGNING_ALLOWED=YES build "$@"
else
    xcodebuild -project OttaiMirror.xcodeproj -scheme OttaiMirror -configuration Release \
        -derivedDataPath build CODE_SIGNING_ALLOWED=NO build "$@"
    codesign --force --sign - --entitlements Widget/Widget.entitlements \
        build/Build/Products/Release/OttaiMirror.app/Contents/PlugIns/OttaiGlucoseWidget.appex
    codesign --force --sign - --entitlements App/App.entitlements build/Build/Products/Release/OttaiMirror.app
fi
codesign --verify --deep --strict build/Build/Products/Release/OttaiMirror.app
printf '%s\n' "Built: $(pwd)/build/Build/Products/Release/OttaiMirror.app"
