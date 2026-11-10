#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
JAVAC=javac
JAVA=java
if [ -n "${JDK:-}" ]; then JAVAC="$JDK/bin/javac"; JAVA="$JDK/bin/java"; fi
mkdir -p android/build/test
"$JAVAC" -d android/build/test android/src/main/java/com/example/glucosewatch6/Reading.java android/test/ReadingTest.java
"$JAVA" -cp android/build/test com.example.glucosewatch6.ReadingTest
"$JAVAC" -d android/build/test android/src/main/java/com/example/glucosewatch6/FaceSyncPolicy.java android/test/FaceSyncPolicyTest.java
"$JAVA" -cp android/build/test com.example.glucosewatch6.FaceSyncPolicyTest
"$JAVAC" -cp android/build/test -d android/build/test android/src/main/java/com/example/glucosewatch6/CloudPolicy.java android/test/CloudPolicyTest.java
"$JAVA" -cp android/build/test com.example.glucosewatch6.CloudPolicyTest
for name in HealthPolicy ActivitySyncPolicy; do
    "$JAVAC" -cp android/build/test -d android/build/test "android/src/main/java/com/example/glucosewatch6/$name.java" "android/test/${name}Test.java"
    "$JAVA" -cp android/build/test "com.example.glucosewatch6.${name}Test"
done
python3 -m unittest server.test_server server.test_activity -q
python3 deploy/relay/test_worker.py
(cd watch && npm test)
python3 tools/test_setup_android.py
