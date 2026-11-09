package com.example.glucosewatch6;

import java.net.URI;

final class CloudPolicy {
    static final int MAX_ATTEMPTS = 8;
    static final int MAX_BODY = 524288;
    static String endpoint(String input) {
        try {
            URI uri = new URI(input.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                    || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
                throw new IllegalArgumentException("请填写 HTTPS 服务地址，不含账号、查询参数或片段");
            String value = uri.toASCIIString();
            while (value.endsWith("/")) value = value.substring(0, value.length()-1);
            return value;
        } catch (java.net.URISyntaxException error) { throw new IllegalArgumentException("服务地址格式无效"); }
    }
    static boolean validToken(String token) {
        return token != null && token.length() >= 16 && token.length() <= 512 && token.matches("[A-Za-z0-9._~+/-]+={0,2}");
    }
    static long delayMillis(int failures) {
        return Math.min(21600000L, 30000L * (1L << Math.min(10, Math.max(0, failures-1))));
    }
    static boolean permanent(int code) { return code >= 400 && code < 500 && code != 408 && code != 429; }
    static boolean validReading(Reading reading, long now) {
        return Reading.validValue(reading.mmol) && reading.sourceAt>0 && reading.sourceAt<=now+90000
            && reading.trend!=null && reading.trend.matches("(?:\\?|[↑↗→↘↓⇈⇊↟↡]{1,32})");
    }
    static String fingerprint(Reading reading) { return Double.toString(reading.mmol)+"|"+reading.trend; }
    static boolean shouldEnqueue(String previous, Reading reading, boolean historical) {
        return previous==null || (!previous.equals(fingerprint(reading)) && !(historical && "?".equals(reading.trend)));
    }
}
