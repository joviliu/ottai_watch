"""Write an ignored build environment for a standard Android SDK; never touches signing keys."""
import argparse
import hashlib
import pathlib
import shlex
import urllib.request

APKSIG_URL = 'https://dl.google.com/dl/android/maven2/com/android/tools/build/apksig/8.13.0/apksig-8.13.0.jar'
APKSIG_SHA256 = 'c070ed1394629d74641aa0906f60b2ffa1ee77e6366a1f93437f59717b1aeb89'


def environment(sdk, jdk, cache):
    platform = sdk / 'platforms/android-35/android.jar'
    build_tools = sdk / 'build-tools/35.0.0'
    result = {
        'JDK': jdk, 'ANDROID_JAR': platform, 'FRAMEWORK_RES': platform,
        'AIDL': build_tools / 'aidl', 'AAPT2': build_tools / 'aapt2',
        'D8_JAR': build_tools / 'lib/d8.jar', 'APKSIG_JAR': cache / 'apksig-8.13.0.jar',
    }
    required = [jdk / 'bin/java', jdk / 'bin/javac'] + [v for k, v in result.items() if k not in ('JDK', 'APKSIG_JAR')]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise ValueError('Install JDK, Android SDK Platform 35 and Build Tools 35.0.0 first. Missing:\n' + '\n'.join(missing))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=pathlib.Path, required=True)
    parser.add_argument('--jdk', type=pathlib.Path, required=True)
    args = parser.parse_args()
    cache = pathlib.Path(__file__).resolve().parents[1] / '.toolchain'
    try:
        env = environment(args.sdk.expanduser().resolve(), args.jdk.expanduser().resolve(), cache)
    except ValueError as error:
        parser.error(str(error))
    cache.mkdir(exist_ok=True)
    jar = env['APKSIG_JAR']
    if not jar.exists():
        with urllib.request.urlopen(APKSIG_URL, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != APKSIG_SHA256:
            raise SystemExit('Downloaded apksig checksum mismatch')
        jar.write_bytes(data)
    if hashlib.sha256(jar.read_bytes()).hexdigest() != APKSIG_SHA256:
        raise SystemExit('Local apksig checksum mismatch; remove it and retry')
    path = cache / 'android.env'
    path.write_text(''.join(f'export {key}={shlex.quote(str(value))}\n' for key, value in env.items()))
    print(f'Environment ready: {path}')


if __name__ == '__main__':
    main()
