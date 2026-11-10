package com.example.glucosewatch6;

public final class ActivitySyncPolicyTest {
    private static void check(boolean value) { if(!value)throw new AssertionError(); }
    public static void main(String[] args) {
        long now=1800000000000L;
        check(ActivitySyncPolicy.due(now,0,false));
        check(!ActivitySyncPolicy.due(now,now-899999,false));
        check(ActivitySyncPolicy.due(now,now-900000,false));
        check(ActivitySyncPolicy.due(now,now-1,true));
        check(ActivitySyncPolicy.due(now,now+3600000,false));
        check(ActivitySyncPolicy.delay(1)==30000);
        long prior=0;
        for(int failures=1;failures<100;failures++) {
            long wait=ActivitySyncPolicy.delay(failures);
            check(wait>=prior && wait<=1800000);prior=wait;
        }
        System.out.println("Activity sync checks passed: cadence, clock rollback, manual refresh, bounded backoff");
    }
}
