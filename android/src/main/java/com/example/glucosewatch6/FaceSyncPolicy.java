package com.example.glucosewatch6;

final class FaceSyncPolicy {
    static String key(long sourceAt, double value, String trend) {
        return sourceAt + "|" + java.math.BigDecimal.valueOf(value).stripTrailingZeros().toPlainString() + "|" + trend;
    }
    static boolean shouldWake(long sourceAt, String frameKey, String exportedKey, long now, long lastWakeAt, String lastWakeKey) {
        return sourceAt > 0 && sourceAt <= now + 90000 && now - sourceAt < 600000
            && !frameKey.equals(exportedKey)
            && (lastWakeAt == 0 || !frameKey.equals(lastWakeKey) || now - lastWakeAt >= 60000);
    }
}
