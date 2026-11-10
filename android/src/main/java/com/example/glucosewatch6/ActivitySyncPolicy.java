package com.example.glucosewatch6;

/** Activity data is batched; glucose/watch delivery never waits for this channel. */
final class ActivitySyncPolicy {
    static final long INTERVAL = 15 * 60 * 1000L;
    static final int MAX_BODY = 4 * 1024 * 1024;
    static boolean due(long now, long previousAttempt, boolean force) {
        return force || previousAttempt <= 0 || now < previousAttempt || now - previousAttempt >= INTERVAL;
    }
    static long delay(int failures) {
        return Math.min(30 * 60 * 1000L, 30000L << Math.min(10, Math.max(0, failures - 1)));
    }
}
