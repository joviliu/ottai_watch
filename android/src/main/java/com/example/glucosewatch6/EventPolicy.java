package com.example.glucosewatch6;

final class EventPolicy {
    static final int MAX_NOTE=1000,MAX_FOODS=1000,MAX_IMAGE=1_048_576,MAX_IMAGE_EDGE=1024;
    static long timeAt(float x,float left,float right,long end) {
        if(right<=left)throw new IllegalArgumentException();
        double f=Math.max(0,Math.min(1,(x-left)/(double)(right-left)));
        long rounded=Math.round((end-86400000L+f*86400000L)/60000.0)*60000L;
        return Math.max(end-86400000L,Math.min(end,rounded));
    }
    /** A cursor may name a nearby observed value, never a value interpolated across a gap. */
    static Reading nearestReading(Iterable<Reading> readings,long at) {
        if(readings==null||at<=0)return null;
        Reading nearest=null;long closest=300001L;
        for(Reading row:readings) {
            if(row==null||row.sourceAt<=0||!Reading.validValue(row.mmol))continue;
            long distance=Math.abs(row.sourceAt-at);
            if(distance<=300000L&&(distance<closest||(distance==closest&&row.sourceAt<nearest.sourceAt))) {
                nearest=row;closest=distance;
            }
        }
        return nearest;
    }
    static boolean horizontal(float dx,float dy,float slop) { return Math.abs(dx)>slop&&Math.abs(dx)>Math.abs(dy); }
    static boolean vertical(float dx,float dy,float slop) { return Math.abs(dy)>slop&&Math.abs(dy)>Math.abs(dx); }
    static boolean validTime(long at,long now) { return at>=now-365L*86400000L&&at<=now+300000L; }
    static boolean validRange(String low,String high) {
        if(low.trim().isEmpty()&&high.trim().isEmpty())return true;
        try { double a=Double.parseDouble(low),b=Double.parseDouble(high);return Double.isFinite(a)&&Double.isFinite(b)&&a>=0&&a<=b&&b<=20000; }
        catch(NumberFormatException e) { return false; }
    }
    static String title(String type) {
        if("meal".equals(type))return "进餐";if("sleep".equals(type))return "入睡";if("wake".equals(type))return "起床";if("exercise".equals(type))return "运动";return "备注";
    }
    static String marker(String type) { return title(type).substring(0,1); }
    private EventPolicy() { }
}
