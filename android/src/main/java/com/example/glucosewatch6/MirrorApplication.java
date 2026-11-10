package com.example.glucosewatch6;

/** Track real activity visibility before any optional Health Connect read begins. */
public final class MirrorApplication extends android.app.Application {
    @Override public void onCreate() {
        super.onCreate();
        HealthConnectBridge.install(this);
    }
}
