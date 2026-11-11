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
        Reading early=new Reading(5.9,end-300000L,"→"),late=new Reading(6.4,end,"→");
        java.util.List<Reading> reversed=java.util.Arrays.asList(late,early);
        check(EventPolicy.nearestReading(reversed,end)==late);
        check(EventPolicy.nearestReading(reversed,end-150000L)==early); // Equal distance chooses earlier sample, independent of input order.
        check(EventPolicy.nearestReading(java.util.Arrays.asList(late),end+300000L)==late);
        check(EventPolicy.nearestReading(java.util.Arrays.asList(late),end+300001L)==null);
        check(EventPolicy.nearestReading(java.util.Arrays.asList(early,new Reading(7.0,end+900000L,"→")),end+300000L)==null);
        check(EventPolicy.nearestReading(java.util.Collections.<Reading>emptyList(),end)==null);
        check(EventPolicy.nearestReading(null,end)==null);
        check(EventPolicy.nearestReading(java.util.Arrays.asList(late),0)==null);
        check(EventPolicy.nearestReading(java.util.Arrays.asList(null,new Reading(Double.NaN,end,"?"),new Reading(0,end,"?"),new Reading(61,end,"?"),new Reading(5.0,0,"?")),end)==null);
        System.out.println("Event policy: time cursor/nearest observed value, scrolling separation and calorie ranges passed");
    }
    private static void check(boolean ok) { if(!ok)throw new AssertionError(); }
}
