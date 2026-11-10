package com.example.glucosewatch6;
public final class EventPolicyTest {
    public static void main(String[] args) {
        long end=1_794_326_400_000L;
        check(EventPolicy.timeAt(20,20,120,end)==end-86400000L);
        check(EventPolicy.timeAt(70,20,120,end)==end-43200000L);
        check(EventPolicy.timeAt(220,20,120,end)==end);
        check(EventPolicy.timeAt(-20,20,120,end)==end-86400000L);
        check(EventPolicy.timeAt(120,20,120,end+47000)==end+47000);
        check(EventPolicy.timeAt(20,20,120,end+17000)>=end+17000-86400000L);
        check(EventPolicy.horizontal(30,6,8)&&!EventPolicy.vertical(30,6,8));
        check(EventPolicy.vertical(6,30,8)&&!EventPolicy.horizontal(6,30,8));
        check(!EventPolicy.horizontal(3,2,8));
        check(EventPolicy.validTime(end,end)&&!EventPolicy.validTime(end+300001,end)&&!EventPolicy.validTime(end-366L*86400000L,end));
        check(EventPolicy.validRange("","")&&EventPolicy.validRange("200","450"));
        check(!EventPolicy.validRange("450","200")&&!EventPolicy.validRange("NaN","400")&&!EventPolicy.validRange("100","")&&!EventPolicy.validRange("-1","10"));
        System.out.println("Event policy: time cursor, scrolling separation and calorie ranges passed");
    }
    private static void check(boolean ok) { if(!ok)throw new AssertionError(); }
}
