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
(cd watch && npm test)
python3 tools/test_setup_android.py
