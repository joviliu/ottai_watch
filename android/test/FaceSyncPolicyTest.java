package com.example.glucosewatch6;

public class FaceSyncPolicyTest {
    public static void main(String[] args) {
        long now=1792972800000L, at=now-20000;
        String key=FaceSyncPolicy.key(at,6.8,"↗");
        if (!FaceSyncPolicy.shouldWake(at,key,"",now,0)) throw new AssertionError("fresh frame needs export");
        if (FaceSyncPolicy.shouldWake(at,key,key,now,0)) throw new AssertionError("exported frame must not wake");
        if (!FaceSyncPolicy.shouldWake(at,FaceSyncPolicy.key(at,6.6,"↘"),key,now,0)) throw new AssertionError("same-time correction must export");
        if (!FaceSyncPolicy.key(at,7.0,"→").equals(at+"|7|→")) throw new AssertionError("JS-compatible numeric key");
        if (FaceSyncPolicy.shouldWake(now-600000,key,"",now,0)) throw new AssertionError("stale frame must not wake");
        if (FaceSyncPolicy.shouldWake(now+90001,key,"",now,0)) throw new AssertionError("future frame must not wake");
        if (FaceSyncPolicy.shouldWake(at,key,"",now,now-59999)) throw new AssertionError("wake cooldown");
        if (!FaceSyncPolicy.shouldWake(at,key,"",now,now-60000)) throw new AssertionError("retry after reconnect cooldown");
        System.out.println("Face sync policy: freshness, export ACK and wake cooldown passed");
    }
}
