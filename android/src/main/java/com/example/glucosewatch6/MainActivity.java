package com.example.glucosewatch6;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.*;
import android.provider.Settings;
import android.widget.*;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.*;

public final class MainActivity extends Activity {
    private TextView reading, details;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        public void run() { render(); handler.postDelayed(this, 60000); }
    };
    private final android.content.SharedPreferences.OnSharedPreferenceChangeListener changed = (prefs, key) -> {
        handler.removeCallbacks(refresh);
        handler.post(refresh);
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        android.service.notification.NotificationListenerService.requestRebind(new android.content.ComponentName(this,OttaiMetadataListener.class));
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(24 * getResources().getDisplayMetrics().density);
        box.setPadding(pad, pad * 2, pad, pad);
        TextView title = new TextView(this); title.setText("血糖镜像 · Redmi Watch 6"); title.setTextSize(22); box.addView(title);
        reading = new TextView(this); reading.setTextSize(46); box.addView(reading);
        details = new TextView(this); details.setTextSize(16); box.addView(details);
        button(box, "启动 / 重新连接", () -> BridgeService.start(this, false));
        button(box, "打开手表应用", () -> BridgeService.start(this, true));
        button(box, "允许读取欧态通知", () -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        Switch faceMode = new Switch(this);
        faceMode.setText("表盘自动同步\n新读数到达且后台未送达时，短暂打开同步并自动返回");
        faceMode.setChecked(getSharedPreferences(ReadingStore.PREFS,0).getBoolean("faceMode",false));
        faceMode.setOnCheckedChangeListener((button,enabled) -> {
            getSharedPreferences(ReadingStore.PREFS,0).edit().putBoolean("faceMode",enabled).apply();
            BridgeService.start(this,false);
        });
        box.addView(faceMode);
        TextView note = new TextView(this);
        note.setText("来源：欧态通知\n无数据时显示 --；超过 10 分钟标记为旧数据。");
        box.addView(note);
        ScrollView scroll = new ScrollView(this); scroll.addView(box); setContentView(scroll);
        ArrayList<String> permissions = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= 31 && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) permissions.add(Manifest.permission.BLUETOOTH_CONNECT);
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) permissions.add(Manifest.permission.POST_NOTIFICATIONS);
        if (!permissions.isEmpty()) requestPermissions(permissions.toArray(new String[0]), 1);
        else BridgeService.start(this, false);
    }
    private void button(LinearLayout box, String label, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setOnClickListener(v -> action.run()); box.addView(button);
    }
    private void render() {
        try {
            String raw = ReadingStore.frame(this);
            String info = "等待真实数据";
            String valueText = "-- mmol/L";
            if (!raw.isEmpty()) {
                JSONObject frame = new JSONObject(raw);
                long at = frame.getLong("sourceAt");
                valueText = String.format(Locale.CHINA, "%.1f %s", frame.getDouble("value"), frame.getString("trend"));
                info = "mmol/L · 欧态更新 " + new SimpleDateFormat("HH:mm", Locale.CHINA).format(new Date(at))
                    + "\n" + Math.max(0, (System.currentTimeMillis() - at) / 60000) + " 分钟前";
                if (System.currentTimeMillis() - at >= 600000) info += " · 旧数据";
                android.content.SharedPreferences prefs = getSharedPreferences(ReadingStore.PREFS, 0);
                if (prefs.getLong("ackSourceAt", 0) == at && prefs.getLong("currentAckAt", 0) > 0) {
                    double seconds = Math.max(0, prefs.getLong("currentAckAt", 0) - frame.getLong("receivedAt")) / 1000.0;
                    info += String.format(Locale.CHINA, "\n手机收到至首次确认 %.1f 秒", seconds);
                } else info += "\n当前读数等待表端确认";
            }
            long ack = getSharedPreferences(ReadingStore.PREFS, 0).getLong("ackAt", 0);
            String detailText = info + "\n\n" + ReadingStore.status(this) + "\n最近表端回执："
                + (ack == 0 ? "尚无" : new SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(new Date(ack))) + "\n";
            if (!android.text.TextUtils.equals(reading.getText(), valueText)) reading.setText(valueText);
            if (!android.text.TextUtils.equals(details.getText(), detailText)) details.setText(detailText);
        } catch (Exception e) { details.setText("数据读取失败：" + e.getClass().getSimpleName()); }
    }
    @Override public void onRequestPermissionsResult(int request, String[] names, int[] grants) {
        super.onRequestPermissionsResult(request, names, grants); BridgeService.start(this, false);
    }
    @Override public void onResume() {
        super.onResume();
        getSharedPreferences(ReadingStore.PREFS, 0).registerOnSharedPreferenceChangeListener(changed);
        handler.post(refresh);
    }
    @Override public void onPause() {
        getSharedPreferences(ReadingStore.PREFS, 0).unregisterOnSharedPreferenceChangeListener(changed);
        handler.removeCallbacks(refresh);
        super.onPause();
    }
}
