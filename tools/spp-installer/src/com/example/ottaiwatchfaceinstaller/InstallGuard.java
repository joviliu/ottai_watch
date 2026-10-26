package com.example.ottaiwatchfaceinstaller;

public final class InstallGuard {
    private InstallGuard() {}
    public static final String PROJECT_FACE_ID = "8670260101";
    public static boolean mode(String mode) {
        return "auth".equals(mode) || "list".equals(mode) || "install".equals(mode) || "replace".equals(mode);
    }
    public static void credentials(String address, String key) {
        if (address == null || !address.matches("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}")) throw new IllegalArgumentException("Invalid device address");
        if (key == null || !key.matches("(?i)[0-9a-f]{32}")) throw new IllegalArgumentException("Invalid auth key format");
    }
    public static void face(boolean valid, String id, int width, int height) {
        if (!valid || !PROJECT_FACE_ID.equals(id) || width != 432 || height != 514)
            throw new IllegalArgumentException("Only this project's 432x514 Ottai watchface is allowed");
    }
    public static String deletionTarget(String id) {
        if (!PROJECT_FACE_ID.equals(id)) throw new IllegalArgumentException("Only the project face can be replaced");
        return PROJECT_FACE_ID;
    }
    public static String safeProgress(String message) {
        if (message == null) return null;
        int raw = message.indexOf(" raw=");
        if (raw >= 0) message = message.substring(0, raw);
        String[] stages = {"Requesting SPP version", "SPP version:", "Upgrading to SPP V2",
            "Authenticated,", "Install start:", "Install reply:", "Watch ready,",
            "Upload reply:", "Upload chunk=", "Upload complete", "Activating watchface", "Done."};
        boolean allowed = false;
        for (String stage : stages) if (message.startsWith(stage)) { allowed = true; break; }
        if (!allowed) return null;
        String lower = message.toLowerCase(java.util.Locale.ROOT);
        if (lower.contains("nonce") || lower.contains("hmac") || lower.contains("authkey")) return null;
        return safeError(new Exception(message));
    }
    public static String safeError(Throwable error) {
        String message = error.getMessage();
        if (message == null) message = error.getClass().getSimpleName();
        message = message.replaceAll("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}", "[device]")
            .replaceAll("(?i)[0-9a-f]{12,}", "[redacted]").replaceAll("[\\r\\n]", " ");
        int raw = message.indexOf(" raw=");
        if (raw >= 0) message = message.substring(0, raw);
        return message.length() > 180 ? message.substring(0, 180) : message;
    }
}
