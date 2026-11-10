package com.example.glucosewatch6;

public final class DetailPolicyTest {
    public static void main(String[] args) {
        String id=repeat('a',64),other=repeat('b',64);
        check(DetailPolicy.path("rolling",id).equals("/api/v1/analysis/detail?kind=rolling&reportId="+id));
        check(DetailPolicy.validIdentity("daily",id));
        check(!DetailPolicy.validIdentity("weekly",id)&&!DetailPolicy.validIdentity("daily",id+"&kind=rolling"));
        check(!DetailPolicy.validIdentity("daily",repeat('a',63))&&!DetailPolicy.validIdentity("daily",null));
        check(DetailPolicy.accepts("daily",id,"daily",id,"ready"));
        check(!DetailPolicy.accepts("daily",id,"rolling",id,"ready")&&!DetailPolicy.accepts("daily",id,"daily",other,"ready"));
        check(!DetailPolicy.accepts("daily",id,"daily",id,"unexpected"));
        check(DetailPolicy.canGenerate("available",true,false,false));
        check(DetailPolicy.canGenerate("ready",true,false,false));
        check(!DetailPolicy.canGenerate("ready",false,false,false));
        check(!DetailPolicy.canGenerate("available",true,true,false)&&!DetailPolicy.canGenerate("available",true,false,true));
        check(!DetailPolicy.canGenerate("running",true,false,false));
        check(DetailPolicy.pollAgain("running",false,179999)&&DetailPolicy.pollAgain("available",true,0));
        check(!DetailPolicy.pollAgain("running",false,180000)&&!DetailPolicy.pollAgain("running",false,-1));
        check(!DetailPolicy.pollAgain("ready",false,1000));
        check(DetailPolicy.textLength("\uD83D\uDE00") == 1&&DetailPolicy.textLength("血糖5.6") == 5);
        check(DetailPolicy.safeSource("https://doi.org/10.2337/dci19-0028"));
        check(DetailPolicy.safeSource("https://www.ncbi.nlm.nih.gov:443/books/NBK278954/#section"));
        for(String url:new String[]{"http://example.com","javascript:alert(1)","intent://example.com","https://user@example.com/a","https://example.com:8443/a","https://example.com/\n"})check(!DetailPolicy.safeSource(url));
        System.out.println("Detailed report policy: pinned identity, explicit generation, bounded polling and HTTPS sources passed");
    }
    private static String repeat(char c,int count) { StringBuilder out=new StringBuilder();while(count-->0)out.append(c);return out.toString(); }
    private static void check(boolean value) { if(!value)throw new AssertionError(); }
}
