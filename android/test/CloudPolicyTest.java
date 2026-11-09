package com.example.glucosewatch6;

public final class CloudPolicyTest {
    private static void check(boolean okay) { if(!okay)throw new AssertionError(); }
    private static void badEndpoint(String text) {
        try { CloudPolicy.endpoint(text);throw new AssertionError("accepted unsafe endpoint"); }
        catch(IllegalArgumentException expected) { }
    }
    public static void main(String[] args) {
        check("https://example.org:8443/ottai".equals(CloudPolicy.endpoint("https://example.org:8443/ottai/")));
        for(String invalid:new String[]{"http://example.org","https://user:secret@example.org","https://example.org?q=secret","https://example.org#secret","file:///tmp/x","https://"})badEndpoint(invalid);
        check(CloudPolicy.validToken("device-upload-test-1234"));
        check(!CloudPolicy.validToken("short")&&!CloudPolicy.validToken("unsafe\r\nAuthorization: secret"));
        long previous=0;
        for(int i=1;i<40;i++) { long delay=CloudPolicy.delayMillis(i);check(delay>=previous&&delay<=21600000);previous=delay; }
        check(CloudPolicy.MAX_ATTEMPTS==8&&CloudPolicy.permanent(401)&&CloudPolicy.permanent(422));
        check(!CloudPolicy.permanent(429)&&!CloudPolicy.permanent(408)&&!CloudPolicy.permanent(503));
        long now=1800000000000L;
        Reading first=new Reading(6.2,now,"→"), changed=new Reading(6.3,now,"↗"), back=new Reading(6.2,now,"→");
        check(CloudPolicy.validReading(first,now));
        Reading repeated=Reading.parseOttai("6.2 mmol/L ↑↑↑ 更新时间：12:00",now,now);
        check(repeated!=null&&"↑↑↑".equals(repeated.trend)&&CloudPolicy.validReading(repeated,now));
        String arrows="";for(int i=0;i<32;i++)arrows+="↓";
        check(CloudPolicy.validReading(new Reading(6.2,now,arrows),now));
        check(!CloudPolicy.validReading(new Reading(6.2,now,arrows+"↓"),now));
        for(Reading invalid:new Reading[]{new Reading(Double.NaN,now,"→"),new Reading(0,now,"→"),new Reading(61,now,"→"),new Reading(6,now+90001,"→"),new Reading(6,now,"malformed"),new Reading(6,now,null)})check(!CloudPolicy.validReading(invalid,now));
        check(CloudPolicy.shouldEnqueue(null,first,false));
        check(!CloudPolicy.shouldEnqueue(CloudPolicy.fingerprint(first),first,false));
        check(CloudPolicy.shouldEnqueue(CloudPolicy.fingerprint(first),changed,false));
        check(CloudPolicy.shouldEnqueue(CloudPolicy.fingerprint(changed),back,false));
        check(!CloudPolicy.shouldEnqueue(CloudPolicy.fingerprint(first),new Reading(6.2,now,"?"),true));
        check(CloudPolicy.shouldEnqueue(null,new Reading(6.2,now,"?"),true));
        System.out.println("Cloud policy checks: HTTPS/auth inputs, bounded retry, invalid readings, duplicate/history suppression and A-to-B-to-A correction passed");
    }
}
