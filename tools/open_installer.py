"""Build the MIT debug-page launcher and open the existing Mi Fitness installer.
Usage: python3 tools/open_installer.py --serial SERIAL --rpk /absolute/file.rpk
Requires JDK, ANDROID_JAR, D8_JAR and adb; does not uninstall or reset anything.
"""
import argparse, os, pathlib, subprocess
parser = argparse.ArgumentParser()
parser.add_argument('--serial',required=True)
target = parser.add_mutually_exclusive_group(required=True)
target.add_argument('--rpk',type=pathlib.Path)
target.add_argument('--watchface',type=pathlib.Path,help='ZIP wrapper produced by watchface/build.py')
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]
build = root/'android/build/launcher'
for name in ('classes','dex'): (build/name).mkdir(parents=True,exist_ok=True)
def run(*parts, capture=False):
    result = subprocess.run([str(part) for part in parts],check=True,text=True,capture_output=capture)
    return result.stdout.strip() if capture else None
adb = ['adb','-s',args.serial]
run(*adb,'get-state')
apk = run(*adb,'shell','pm','path','com.xiaomi.wearable',capture=True)
if not apk.startswith('package:') or '\n' in apk: raise SystemExit('Expected one installed com.xiaomi.wearable APK')
apk = apk[len('package:'):]
source = args.rpk or args.watchface
if not source.is_file(): raise SystemExit('Install file not found')
jdk = pathlib.Path(os.environ['JDK'])/'bin'
run(jdk/'javac','--release','8','-classpath',os.environ['ANDROID_JAR'],'-d',build/'classes',root/'tools/LaunchFragment.java')
run(jdk/'java','-cp',os.environ['D8_JAR'],'com.android.tools.r8.D8','--lib',os.environ['ANDROID_JAR'],'--min-api','26','--output',build/'dex',build/'classes/LaunchFragment.class')
run(*adb,'push',build/'dex/classes.dex','/data/local/tmp/glucose-watch6-launch.dex')
remote = '/sdcard/Download/glucose-watch6.rpk' if args.rpk else '/sdcard/Download/ottai-minimal-watch6.zip'
run(*adb,'push',source.resolve(),remote)
fragment = 'com.xiaomi.xms.wearable.ui.debug.ThirdAppDebugFragment' if args.rpk else 'com.xiaomi.fitness.watch.face.debug.designer.FaceDesignerFragment'
run(*adb,'shell','env','CLASSPATH=/data/local/tmp/glucose-watch6-launch.dex','app_process','/','LaunchFragment',apk,fragment)
print('Installer opened; select the file in Downloads and verify the install result. Opening the page does not confirm installation.')
