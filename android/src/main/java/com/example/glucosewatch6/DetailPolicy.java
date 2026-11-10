package com.example.glucosewatch6;

import java.net.URI;

/** Identity and paid-action boundaries shared by the detail viewer and host checks. */
final class DetailPolicy {
    static final long POLL_LIMIT_MS=180000;
    static boolean validIdentity(String kind,String id) {
        return ("rolling".equals(kind)||"daily".equals(kind))&&id!=null&&id.matches("[a-f0-9]{64}");
    }
    static String path(String kind,String id) {
        if(!validIdentity(kind,id))throw new IllegalArgumentException();
        return "/api/v1/analysis/detail?kind="+kind+"&reportId="+id;
    }
    static boolean accepts(String expectedKind,String expectedId,String kind,String id,String status) {
        return validIdentity(kind,id)&&kind.equals(expectedKind)&&id.equals(expectedId)&&
            ("available".equals(status)||"running".equals(status)||"ready".equals(status)||"error".equals(status)||"unavailable".equals(status));
    }
    static boolean canGenerate(String status,boolean eligible,boolean unconfirmed,boolean busy) {
        return eligible&&!unconfirmed&&!busy&&("available".equals(status)||"ready".equals(status)||"error".equals(status));
    }
    static boolean pollAgain(String status,boolean unconfirmed,long elapsed) {
        return ("running".equals(status)||unconfirmed)&&elapsed>=0&&elapsed<POLL_LIMIT_MS;
    }
    static boolean safeSource(String value) {
        try {
            URI uri=new URI(value);
            return value.length()<=2000&&"https".equals(uri.getScheme())&&uri.getHost()!=null&&uri.getUserInfo()==null&&(uri.getPort()==-1||uri.getPort()==443);
        }catch(Exception ignored) { return false; }
    }
    static int textLength(String value) { return value.codePointCount(0,value.length()); }
    private DetailPolicy() { }
}
