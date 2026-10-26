import pathlib
import tempfile
import unittest
from setup_android import environment


class EnvironmentTest(unittest.TestCase):
    def test_standard_sdk_and_missing_tools(self):
        with tempfile.TemporaryDirectory(prefix='ottai sdk ') as directory:
            root = pathlib.Path(directory)
            sdk, jdk = root / 'sdk', root / 'jdk'
            with self.assertRaisesRegex(ValueError, 'Missing'):
                environment(sdk, jdk, root / '.toolchain')
            for path in ['jdk/bin/java', 'jdk/bin/javac', 'sdk/platforms/android-35/android.jar',
                         'sdk/build-tools/35.0.0/aidl', 'sdk/build-tools/35.0.0/aapt2', 'sdk/build-tools/35.0.0/lib/d8.jar']:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            result = environment(sdk, jdk, root / '.toolchain')
            self.assertEqual(result['ANDROID_JAR'], result['FRAMEWORK_RES'])
            self.assertEqual(result['AIDL'], sdk / 'build-tools/35.0.0/aidl')


if __name__ == '__main__':
    unittest.main()
