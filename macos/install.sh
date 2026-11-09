#!/bin/sh
set -eu
cd "$(dirname "$0")"
source_app="$(pwd)/build/Build/Products/Release/OttaiMirror.app"
target="${HOME}/Applications/OttaiMirror.app"
if [ ! -d "$source_app" ]; then echo 'Run sh macos/build.sh first.' >&2; exit 1; fi
if [ "$#" -ne 0 ]; then
    if [ "$#" -ne 2 ] || [ "$1" != '--import-config' ]; then echo 'Usage: install.sh [--import-config private.json]' >&2; exit 1; fi
    python3 configure.py "$2"
else
    python3 configure.py
fi
mkdir -p "${HOME}/Applications"
if [ -d "$target" ]; then
    echo 'Quit the existing OttaiMirror before replacement.'
    pkill -x OttaiMirror 2>/dev/null || true
    for attempt in 1 2 3 4 5; do
        if ! pgrep -x OttaiMirror >/dev/null; then break; fi
        sleep 1
    done
    if pgrep -x OttaiMirror >/dev/null; then echo "Existing app has not exited; replacement cancelled." >&2; exit 1; fi
    pkill -x OttaiGlucoseWidget 2>/dev/null || true
fi
ditto "$source_app" "$target"
codesign --verify --deep --strict "$target"
mkdir -p "${HOME}/Library/LaunchAgents"
python3 - "$target" <<'PY'
import os,pathlib,plistlib,sys
target=pathlib.Path(sys.argv[1]);path=pathlib.Path.home()/'Library/LaunchAgents/com.joviliu.ottai.mirror.plist'
path.write_bytes(plistlib.dumps({'Label':'com.joviliu.ottai.mirror','ProgramArguments':[str(target/'Contents/MacOS/OttaiMirror')], 'RunAtLoad':True,'ProcessType':'Background'}))
os.chmod(path,0o600)
PY
build_extension="$source_app/Contents/PlugIns/OttaiGlucoseWidget.appex"
pluginkit -r "$build_extension" 2>/dev/null || true
/System/Library/Frameworks/CoreServices.framework/Versions/Current/Frameworks/LaunchServices.framework/Versions/Current/Support/lsregister -u "$source_app" 2>/dev/null || true
/System/Library/Frameworks/CoreServices.framework/Versions/Current/Frameworks/LaunchServices.framework/Versions/Current/Support/lsregister -f "$target"
pluginkit -a "$target/Contents/PlugIns/OttaiGlucoseWidget.appex"
open "$target"
printf '%s\n' "Installed menu app and next-login LaunchAgent: $target"
printf '%s\n' 'Add the real widget from Notification Center → Edit Widgets → 血糖镜像.'
