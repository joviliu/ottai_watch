package com.example.glucosewatch6;

public final class HealthPolicyTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    private static void reject(Runnable operation) {
        try { operation.run(); throw new AssertionError("accepted incomplete or excessive snapshot"); }
        catch (IllegalArgumentException expected) { }
    }
    public static void main(String[] args) {
        check(HealthPolicy.WINDOW_MILLIS == 48L * 60 * 60 * 1000);
        check(!HealthPolicy.supportsExtendedReads(33, 99));
        check(!HealthPolicy.supportsExtendedReads(34, 12));
        check(HealthPolicy.supportsExtendedReads(34, 13));
        check(HealthPolicy.supportsExtendedReads(36, 20));
        check(HealthPolicy.validWindow(1000, 1000 + HealthPolicy.WINDOW_MILLIS));
        check(!HealthPolicy.validWindow(0, 1000));
        check(!HealthPolicy.validWindow(1000, 1000));
        check(!HealthPolicy.validWindow(1000, 1000 + HealthPolicy.WINDOW_MILLIS + 1));
        check(HealthPolicy.activeKilocalories(0) == 0);
        check(HealthPolicy.activeKilocalories(1000) == 1);
        check(HealthPolicy.activeKilocalories(335330) == 335.33); // Unit conversion, not335330kcal.
        check(HealthPolicy.activeKilocalories(100000000) == 100000);
        reject(() -> HealthPolicy.activeKilocalories(100000001));
        reject(() -> HealthPolicy.activeKilocalories(-1));
        reject(() -> HealthPolicy.activeKilocalories(-Double.MIN_VALUE));
        reject(() -> HealthPolicy.activeKilocalories(Double.NaN));
        reject(() -> HealthPolicy.activeKilocalories(Double.POSITIVE_INFINITY));
        reject(() -> HealthPolicy.activeKilocalories(Double.NEGATIVE_INFINITY));

        HealthPolicy.Budget paging = new HealthPolicy.Budget();
        paging.page(-1); paging.page(12); paging.page(19);
        reject(() -> paging.page(12)); // A non-adjacent repeated token must never loop forever.
        paging.nextKind(); paging.page(-1); paging.page(12); // Tokens may repeat across different record types.
        HealthPolicy.Budget pages = new HealthPolicy.Budget();
        for (int i = 0; i < HealthPolicy.MAX_PAGES; i++) pages.page(i);
        reject(() -> pages.page(HealthPolicy.MAX_PAGES));

        HealthPolicy.Budget samples = new HealthPolicy.Budget();
        samples.record("heart_rate", "a", 60000, 100);
        samples.record("heart_rate", "b", 40000, 100);
        check(samples.sampleCount() == 100000 && samples.recordCount() == 2);
        reject(() -> samples.record("heart_rate", "c", 1, 100));
        HealthPolicy.Budget ids = new HealthPolicy.Budget();
        ids.record("steps", "a", 0, 100);
        ids.record("exercise", "a", 0, 100);
        reject(() -> ids.record("steps", "a", 0, 100));
        reject(() -> new HealthPolicy.Budget().record("steps", "", 0, 100));
        reject(() -> new HealthPolicy.Budget().record("steps", "a", -1, 100));
        reject(() -> new HealthPolicy.Budget().record("steps", "a", 0, Integer.MAX_VALUE));
        HealthPolicy.Budget bytes = new HealthPolicy.Budget();
        bytes.record("steps", "a", 0, HealthPolicy.MAX_BYTES - 4097);
        reject(() -> bytes.record("steps", "b", 0, 1));
        HealthPolicy.Budget records = new HealthPolicy.Budget();
        for (int i = 0; i < HealthPolicy.MAX_RECORDS; i++) records.record("steps", Integer.toString(i), 0, 1);
        reject(() -> records.record("steps", "overflow", 0, 1));
        System.out.println("Health policy: extension availability, rolling window, repeated tokens, cal-to-kcal conversion/energy bounds, total page/record/sample/UTF8 byte bounds passed");
    }
}
