"""Build the independent AGPL development installer using the project's Android toolchain."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
BC_URL='https://repo.maven.apache.org/maven2/org/bouncycastle/bcprov-jdk18on/1.78.1/bcprov-jdk18on-1.78.1.jar'
BC_SHA256='add5915e6acfc6ab5836e1fd8a5e21c6488536a8c1f21f386eeb3bf280b702d7'


def run(*parts):
    subprocess.run([str(x) for x in parts],check=True)


def build():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bc-jar',type=Path,help='Optional existing official bcprov 1.78.1 jar (checksum checked)')
    parser.add_argument('--face',type=Path,help='Optional project BIN to validate before producing APK')
    args=parser.parse_args()
    env={k:os.environ[k] for k in ['JDK','ANDROID_JAR','FRAMEWORK_RES','AAPT2','D8_JAR','APKSIG_JAR']}
    jdk=Path(env['JDK'])/'bin'
    output=ROOT/'build';output.mkdir(exist_ok=True)
    for child in ['classes','test','dex']:
        folder=output/child
        if folder.exists():shutil.rmtree(folder)
        folder.mkdir()
    bc=args.bc_jar.resolve() if args.bc_jar else output/'bcprov-jdk18on-1.78.1.jar'
    if not bc.exists():
        with urllib.request.urlopen(BC_URL,timeout=60) as response:data=response.read()
        if hashlib.sha256(data).hexdigest()!=BC_SHA256:raise SystemExit('BouncyCastle download checksum mismatch')
        bc.write_bytes(data)
    if hashlib.sha256(bc.read_bytes()).hexdigest()!=BC_SHA256:raise SystemExit('BouncyCastle checksum mismatch')
    sources=list((ROOT/'src').rglob('*.java'))
    # No runtime credentials or device identifiers may be embedded in source/assets.
    for source in sources:
        text=source.read_text()
        if 'DEFAULT_AUTH' in text or 'DEFAULT_MAC' in text:raise SystemExit('Unexpected embedded default credential')
    if list(ROOT.rglob('auth.json')):raise SystemExit('Never place runtime auth.json in this source component')
    run(jdk/'javac','--release','8','-classpath',env['ANDROID_JAR']+os.pathsep+str(bc),'-d',output/'classes',*sources)
    run(jdk/'javac','--release','8','-classpath',str(output/'classes')+os.pathsep+env['ANDROID_JAR'],'-d',output/'test',ROOT/'test/InstallGuardTest.java')
    test=[jdk/'java','-cp',str(output/'test')+os.pathsep+str(output/'classes')+os.pathsep+env['ANDROID_JAR'],'com.example.ottaiwatchfaceinstaller.InstallGuardTest']
    if args.face:test.append(args.face.resolve())
    run(*test)
    classes=output/'classes.jar'
    with zipfile.ZipFile(classes,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in (output/'classes').rglob('*.class'):archive.write(file,file.relative_to(output/'classes'))
    # Multi-release JAR variants duplicate class names in DEX; Android uses the Java 8 base classes.
    base_bc=output/'bcprov-android.jar'
    with zipfile.ZipFile(bc) as source,zipfile.ZipFile(base_bc,'w',zipfile.ZIP_DEFLATED) as dest:
        for name in source.namelist():
            if name.endswith('.class') and not name.startswith('META-INF/') and name!='module-info.class':dest.writestr(name,source.read(name))
    run(jdk/'java','-cp',env['D8_JAR'],'com.android.tools.r8.D8','--lib',env['ANDROID_JAR'],'--min-api','26','--output',output/'dex',classes,base_bc)
    unsigned=output/'unsigned.apk'
    if unsigned.exists():unsigned.unlink()
    run(env['AAPT2'],'link','-I',env['FRAMEWORK_RES'],'--manifest',ROOT/'AndroidManifest.xml','-o',unsigned)
    with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as archive:
        for dex in sorted((output/'dex').glob('*.dex')):archive.write(dex,dex.name)
        for notice in ['LICENSE','BC-LICENSE.txt','NOTICE.md']:
            archive.write(ROOT/notice,'assets/licenses/'+notice)
    signed=output/'ottai-watchface-installer.apk'
    run(jdk/'java','-cp',env['APKSIG_JAR'],PROJECT/'tools/SignApk.java',PROJECT/'.sign/private.pem',PROJECT/'.sign/certificate.pem',unsigned,signed)
    print(signed)
    print('sha256',hashlib.sha256(signed.read_bytes()).hexdigest())


if __name__=='__main__':build()
