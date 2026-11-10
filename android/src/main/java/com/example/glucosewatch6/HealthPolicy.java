package com.example.glucosewatch6;

import java.util.HashSet;
import java.util.Set;

/** Bounds and paging invariants shared by the native reader and host-side tests. */
public final class HealthPolicy {
    private HealthPolicy() { }
    public static final String ORIGIN = "com.mi.health";
    public static final long WINDOW_MILLIS = 48L * 60 * 60 * 1000;
    public static final int MAX_RECORDS = 10000;
    public static final int MAX_SAMPLES = 100000;
    public static final int MAX_BYTES = 4 * 1024 * 1024;
    public static final int MAX_PAGES = 400;
    public static final long TIMEOUT_MILLIS = 120000;

    public static boolean supportsExtendedReads(int sdk, int uExtension) {
        return sdk >= 34 && uExtension >= 13;
    }

    public static boolean validWindow(long start, long end) {
        return start > 0 && end > start && end - start <= WINDOW_MILLIS;
    }

    /** Failing a limit invalidates the entire snapshot; never trim or emit a partial scan. */
    public static final class Budget {
        private int records, samples, bytes = 4096, pages;
        private final Set<String> ids = new HashSet<>();
        private final Set<Long> tokens = new HashSet<>();

        public void page(long requestedToken) {
            if (++pages > MAX_PAGES || !tokens.add(requestedToken))
                throw new IllegalArgumentException("paging_limit");
        }

        public void nextKind() { tokens.clear(); }

        public void record(String kind, String id, int sampleCount, int byteCount) {
            if (id == null || id.isEmpty() || sampleCount < 0 || byteCount < 0)
                throw new IllegalArgumentException("invalid_record");
            if (!ids.add(kind + ":" + id)) throw new IllegalArgumentException("duplicate_record");
            if (++records > MAX_RECORDS || sampleCount > MAX_SAMPLES - samples
                    || byteCount + 1L > MAX_BYTES - bytes)
                throw new IllegalArgumentException("snapshot_limit");
            samples += sampleCount;
            bytes += byteCount + 1;
        }

        public int recordCount() { return records; }
        public int sampleCount() { return samples; }
    }
}
