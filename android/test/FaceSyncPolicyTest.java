package com.example.glucosewatch6;

public class FaceSyncPolicyTest {
    public static void main(String[] args) {
        long now=1792972800000L, at=now-20000;
        String key=FaceSyncPolicy.key(at,6.8,"↗");
        if (!FaceSyncPolicy.shouldWake(at,key,"",now,0,null)) throw new AssertionError("fresh frame needs export");
        if (FaceSyncPolicy.shouldWake(at,key,key,now,0,null)) throw new AssertionError("exported frame must not wake");
        if (!FaceSyncPolicy.shouldWake(at,FaceSyncPolicy.key(at,6.6,"↘"),key,now,0,null)) throw new AssertionError("same-time correction must export");
        if (!FaceSyncPolicy.key(at,7.0,"→").equals(at+"|7|→")) throw new AssertionError("JS-compatible numeric key");
        if (FaceSyncPolicy.shouldWake(now-600000,key,"",now,0,null)) throw new AssertionError("stale frame must not wake");
        if (FaceSyncPolicy.shouldWake(now+90001,key,"",now,0,null)) throw new AssertionError("future frame must not wake");
        if (FaceSyncPolicy.shouldWake(at,key,"",now,now-59999,key)) throw new AssertionError("same frame wake cooldown");
        if (!FaceSyncPolicy.shouldWake(at,key,"",now,now-60000,key)) throw new AssertionError("same frame retries at cooldown boundary");
        String olderKey=FaceSyncPolicy.key(at-300000,6.8,"↗");
        if (!FaceSyncPolicy.shouldWake(at,key,"",now,now-1,olderKey)) throw new AssertionError("new source must not inherit prior frame cooldown");
        if (!FaceSyncPolicy.shouldWake(at,FaceSyncPolicy.key(at,6.9,"↗"),"",now,now-1,key)) throw new AssertionError("value correction must not inherit prior frame cooldown");
        if (!FaceSyncPolicy.shouldWake(at,FaceSyncPolicy.key(at,6.8,"→"),"",now,now-1,key)) throw new AssertionError("trend correction must not inherit prior frame cooldown");
        if (!FaceSyncPolicy.shouldWake(at,key,"",now,now-1,null)) throw new AssertionError("unknown previous identity must not block first wake");
        if (FaceSyncPolicy.shouldWake(at,key,key,now,now-1,olderKey)) throw new AssertionError("export ACK still wins over new identity");
        if (FaceSyncPolicy.shouldWake(now-600000,key,"",now,now-1,olderKey)) throw new AssertionError("new identity does not bypass freshness");
        if (FaceSyncPolicy.shouldWake(now+90001,key,"",now,now-1,olderKey)) throw new AssertionError("new identity does not bypass future guard");
        System.out.println("Face sync policy: freshness, export ACK and per-frame wake cooldown passed");
    }
}
