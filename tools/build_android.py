"""Build with a local JDK, Android platform jar, aidl, aapt2, D8 and apksig.
Paths are explicit environment variables; no credentials or signing keys are embedded.
"""
import os, pathlib, subprocess, zipfile, shutil, xml.etree.ElementTree as ET
root = pathlib.Path(__file__).resolve().parents[1]
build = root / 'android/build'
if build.exists(): shutil.rmtree(build)
for name in ('classes','generated','dex','test'):
    (build / name).mkdir(parents=True,exist_ok=True)
def run(*args):
    subprocess.run([str(arg) for arg in args],check=True)
env = {key:os.environ[key] for key in ('JDK','ANDROID_JAR','FRAMEWORK_RES','AIDL','AAPT2','D8_JAR','APKSIG_JAR')}
java = pathlib.Path(env['JDK']) / 'bin/java'
javac = pathlib.Path(env['JDK']) / 'bin/javac'
sources = root/'android/src/main/java'
unsigned = build/'unsigned.apk'
resources = build/'resources.zip'
run(env['AAPT2'],'compile','--dir',root/'android/src/main/res','-o',resources)
run(env['AAPT2'],'link','-I',env['FRAMEWORK_RES'],'--manifest',root/'android/src/main/AndroidManifest.xml',resources,'--java',build/'generated','-o',unsigned)
run(javac,'-d',build/'test',sources/'com/example/glucosewatch6/Reading.java',root/'android/test/ReadingTest.java')
run(java,'-cp',build/'test','com.example.glucosewatch6.ReadingTest')
sdk = root/'android/vendor/sdk/main'
framework = build/'framework.aidl'
framework.write_text('parcelable android.os.Bundle;\n')
interfaces = [path for path in (sdk/'aidl').rglob('*.aidl') if 'interface ' in path.read_text()]
run(env['AIDL'],'--lang=java','--min_sdk_version=26','-I',sdk/'aidl','-p',framework,'-o',build/'generated',*interfaces)
java_sources = list(sources.rglob('*.java')) + list((sdk/'java/com').rglob('*.java')) + list((build/'generated').rglob('*.java'))
run(javac,'--release','8','-classpath',env['ANDROID_JAR'],'-d',build/'classes',*java_sources)
classes = build/'classes.jar'
with zipfile.ZipFile(classes,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in (build/'classes').rglob('*.class'):
        archive.write(path,path.relative_to(build/'classes'))
run(java,'-cp',env['D8_JAR'],'com.android.tools.r8.D8','--lib',env['ANDROID_JAR'],'--min-api','26','--output',build/'dex',classes)
with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as archive:
    archive.write(build/'dex/classes.dex','classes.dex')
manifest = ET.parse(root/'android/src/main/AndroidManifest.xml').getroot()
version = manifest.attrib['{http://schemas.android.com/apk/res/android}versionName']
signed = build/f'glucose-watch6-{version}.apk'
run(java,'-cp',env['APKSIG_JAR'],root/'tools/SignApk.java',root/'.sign/private.pem',root/'.sign/certificate.pem',unsigned,signed)
print(signed)
