package com.example.glucosewatch6;

public final class PhoneStepsPolicyTest {
    private static final long END = 1800000000000L, START = END - PhoneStepsPolicy.WINDOW_MILLIS;
    private static void reject(Runnable operation) {
        try { operation.run(); throw new AssertionError("invalid or partial phone step snapshot accepted"); }
        catch (IllegalArgumentException expected) { }
    }
    public static void main(String[] args) {
        PhoneStepsPolicy.validate(0, START, START, 0, 1, START, END); // Explicit zero/instant row remains real data.
        PhoneStepsPolicy.validate(1, START, END, 1234, 2, START, END);
        PhoneStepsPolicy.validate(2, END - 1, END + 90000, 2000000, 1000, START, END);
        reject(() -> PhoneStepsPolicy.validate(-1, START, END, 3, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START - 1, END, 3, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, END, END, 3, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START / 1000, END / 1000, 3, 2, START, END)); // Seconds must never be silently reinterpreted.
        reject(() -> PhoneStepsPolicy.validate(1, START * 1000, END * 1000, 3, 2, START, END)); // Nor microseconds.
        reject(() -> PhoneStepsPolicy.validate(1, START, START - 1, 3, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START, END + 1, 3, 2, START, END)); // Longer than48h interval.
        reject(() -> PhoneStepsPolicy.validate(1, END - 1, END + 90001, 3, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START, END, -1, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START, END, 2000001, 2, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START, END, 3, -1, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START, END, 3, 1001, START, END));
        reject(() -> PhoneStepsPolicy.validate(1, START, END, 3, 2, START - 1, END));
        PhoneStepsPolicy.Budget duplicates = new PhoneStepsPolicy.Budget(); duplicates.row(1); reject(() -> duplicates.row(1));
        PhoneStepsPolicy.Budget records = new PhoneStepsPolicy.Budget();
        for (int i = 0; i < PhoneStepsPolicy.MAX_RECORDS; i++) records.row(i);
        reject(() -> records.row(PhoneStepsPolicy.MAX_RECORDS));
        PhoneStepsPolicy.Budget bytes = new PhoneStepsPolicy.Budget(); bytes.bytes(PhoneStepsPolicy.MAX_BYTES - 4097);
        reject(() -> bytes.bytes(1));
        reject(() -> new PhoneStepsPolicy.Budget().bytes(Integer.MAX_VALUE));
        reject(() -> new PhoneStepsPolicy.Budget().bytes(-1));
        System.out.println("Phone steps: original48hSTART intervals, units, explicitzero, invalidrows, duplicateIDs, complete-snapshot record/byte bounds passed");
    }
}
