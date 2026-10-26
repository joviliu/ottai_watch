package com.example.glucosewatch6;

import android.app.Notification;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

public final class OttaiMetadataListener extends NotificationListenerService {
    @Override public void onListenerConnected() {
        android.util.Log.i("GlucoseWatch6", "LISTENER_CONNECTED");
        StatusBarNotification[] active = getActiveNotifications();
        if (active != null) for (StatusBarNotification notification : active) onNotificationPosted(notification);
    }

    @Override public void onListenerDisconnected() {
        android.util.Log.i("GlucoseWatch6", "LISTENER_DISCONNECTED; requesting rebind");
        try { requestRebind(new android.content.ComponentName(this, OttaiMetadataListener.class)); }
        catch (RuntimeException error) { android.util.Log.w("GlucoseWatch6", "Listener rebind unavailable: "+error.getClass().getSimpleName()); }
    }

    @Override public void onNotificationPosted(StatusBarNotification sbn) {
        if (!"com.ottai.tag".equals(sbn.getPackageName())) return;
        Notification n = sbn.getNotification();
        CharSequence text = n.extras.getCharSequence(Notification.EXTRA_TEXT);
        long at = n.when > 0 ? n.when : sbn.getPostTime();
        long observedAt = System.currentTimeMillis();
        Reading reading = Reading.parseOttai(text == null ? null : text.toString(), at, observedAt);
        if (reading != null && ReadingStore.metadata(this, reading)) {
            android.util.Log.i("GlucoseWatch6", "Ottai sourceAt=" + reading.sourceAt + " notificationAt=" + at
                + " observedAt=" + observedAt + " value=" + reading.mmol + " trend=" + reading.trend);
            BridgeService.updated(this);
        }
    }
}
