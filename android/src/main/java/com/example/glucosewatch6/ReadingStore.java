package com.example.glucosewatch6;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import org.json.JSONObject;

final class ReadingStore {
    static final String PREFS = "glucose_watch6";
    private static SharedPreferences prefs(Context c) { return c.getSharedPreferences(PREFS, 0); }

    static synchronized boolean metadata(Context c, Reading reading) {
        SharedPreferences p = prefs(c);
        Reading source = reading;
        if (!Reading.validValue(source.mmol) || source.sourceAt <= 0 || source.sourceAt > System.currentTimeMillis() + 90000) return false;
        try {
            String previous = p.getString("frame", "");
            if (!previous.isEmpty()) {
                JSONObject old = new JSONObject(previous);
                if (old.getLong("sourceAt") > source.sourceAt) return false;
                if (old.getLong("sourceAt") == source.sourceAt && Math.abs(old.getDouble("value") - source.mmol) < 0.001
                        && old.getString("trend").equals(source.trend)) return false;
            }
            JSONArray history = new JSONArray(p.getString("history", "[]"));
            JSONArray next = new JSONArray();
            for (int i = Math.max(0, history.length() - 23); i < history.length(); i++) {
                JSONObject item = history.getJSONObject(i);
                if (item.getLong("time") < source.sourceAt) next.put(item);
            }
            next.put(new JSONObject().put("time", source.sourceAt).put("value", source.mmol));
            JSONObject frame = new JSONObject().put("type", "glucose").put("version", 1)
                .put("value", source.mmol).put("unit", "mmol/L").put("trend", source.trend)
                .put("sourceAt", source.sourceAt).put("source", "ottai_notification")
                .put("receivedAt", System.currentTimeMillis()).put("history", next);
            p.edit().putString("frame", frame.toString()).putString("history", next.toString()).putLong("currentAckAt", 0).apply();
            status(c, "欧态真实读数已接收，等待表端回执");
            return true;
        } catch (Exception e) {
            status(c, "读取历史失败：" + e.getClass().getSimpleName());
            return false;
        }
    }

    static String frame(Context c) { return prefs(c).getString("frame", ""); }
    static void status(Context c, String text) {
        prefs(c).edit().putString("status", text).apply();
        android.util.Log.i("GlucoseWatch6", text);
    }
    static String status(Context c) { return prefs(c).getString("status", "尚未启动"); }
    static synchronized void ack(Context c, long sourceAt) {
        long now = System.currentTimeMillis();
        SharedPreferences p = prefs(c);
        SharedPreferences.Editor edit = p.edit().putLong("ackSourceAt", sourceAt).putLong("ackAt", now);
        if (p.getLong("currentAckAt", 0) == 0) edit.putLong("currentAckAt", now);
        edit.apply();
        try {
            JSONObject frame = new JSONObject(frame(c));
            android.util.Log.i("GlucoseWatch6", "ACK sourceAt=" + sourceAt + " value=" + frame.getDouble("value")
                + " receivedAt=" + frame.getLong("receivedAt") + " ackAt=" + now
                + " elapsedMs=" + (now - frame.getLong("receivedAt")));
        } catch (Exception ignored) { }
        status(c, "表端已确认接收来源时间：" + new java.text.SimpleDateFormat("HH:mm", java.util.Locale.CHINA).format(new java.util.Date(sourceAt)));
    }
}
