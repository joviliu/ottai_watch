package com.example.glucosewatch6;

import java.util.HashSet;
import java.util.Set;

/** Validation for Xiaomi's original interval rows. Never estimate missing steps or rescale time. */
public final class PhoneStepsPolicy {
    private PhoneStepsPolicy() { }
    public static final long WINDOW_MILLIS = 48L * 60 * 60 * 1000;
    public static final long TIMEOUT_MILLIS = 30000;
    public static final int MAX_RECORDS = 10000;
    public static final int MAX_BYTES = 4 * 1024 * 1024;
    private static final long YEAR_2000_MILLIS = 946684800000L;

    public static void validate(long id, long start, long end, long count, long mode,
            long windowStart, long windowEnd) {
        if (windowStart < YEAR_2000_MILLIS || windowEnd <= windowStart
                || windowEnd - windowStart > WINDOW_MILLIS || id < 0
                || start < windowStart || start >= windowEnd || end < start
                || end - start > WINDOW_MILLIS || end > windowEnd + 90000L
                || count < 0 || count > 2000000 || mode < 0 || mode > 1000)
            throw new IllegalArgumentException("invalid_phone_steps_record");
    }

    public static final class Budget {
        private final Set<Long> ids = new HashSet<>();
        private int bytes = 4096;
        public void row(long id) {
            if (ids.size() >= MAX_RECORDS || !ids.add(id)) throw new IllegalArgumentException("snapshot_limit");
        }
        public void bytes(int amount) {
            if (amount < 0 || amount + 1L > MAX_BYTES - bytes) throw new IllegalArgumentException("snapshot_limit");
            bytes += amount + 1;
        }
    }
}
