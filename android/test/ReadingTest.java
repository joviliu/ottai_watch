package com.example.glucosewatch6;
import java.util.*;
public class ReadingTest {
    static long at(int day, int hour, int minute) {
        Calendar c = Calendar.getInstance(); c.clear(); c.set(2026,9,day,hour,minute); return c.getTimeInMillis();
    }
    static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
    public static void main(String[] args) {
        TimeZone.setDefault(TimeZone.getTimeZone("Asia/Shanghai"));
        long now = at(26,12,0);
        Reading r = Reading.parseOttai("5.6 mmol/L → · 更新时间：11:53",now,now);
        check(r != null && r.mmol == 5.6 && r.sourceAt == at(26,11,53) && r.trend.equals("→"),"real notification");
        check(Reading.parseOttai("0 mmol/L → 更新时间：11:53",now,now) == null,"no zero placeholder");
        check(Reading.parseOttai("-5.6 mmol/L → 更新时间：11:53",now,now) == null,"negative value");
        check(Reading.parseOttai("5.6 mmol/L → 更新时间：11:53",now+120000,now) == null,"future notification");
        check(Reading.parseOttai("5.6 mg/dL 更新时间：11:53",now,now) == null,"require correct unit");
        check(Reading.parseOttai("5.6 mmol/L 5.7 mmol/L 更新时间：11:53",now,now) == null,"ambiguous value");
        check(Reading.parseOttai("5.6 mmol/L 更新时间：24:03",now,now) == null,"invalid time");
        Reading midnight = Reading.parseOttai("5.6 mmol/L 更新时间：23:58",at(27,0,1),at(27,0,1));
        check(midnight.sourceAt == at(26,23,58),"midnight rollover");
        Reading old = Reading.parseOttai("5.6 mmol/L 更新时间：11:53",now,at(26,16,0));
        check(old.sourceAt == r.sourceAt,"repost does not become fresh");
        check(!Reading.validValue(Double.NaN),"NaN");
        System.out.println("Android reading parser: values, units and timestamp checks passed");
    }
}
