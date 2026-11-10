package com.example.glucosewatch6;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

/** Health permission rationale and opt-in settings. Merely opening this screen never grants access. */
public final class HealthActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status, upload;
    private Button background, sync;
    private final Runnable refresh = new Runnable() {
        public void run() { render(); handler.postDelayed(this, 3000); }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout page = MobileStyle.page(this);
        label(page, "运动与血糖", 28, 0xff233456, true);
        label(page, "结合运动、心率和步数，让每日观察多一份时间线索。", 15, 0xff66789a, false);

        LinearLayout connection = card(page);
        Switch enabled = new Switch(this); enabled.setText("启用运动辅助分析"); enabled.setTextSize(17);
        enabled.setTextColor(0xff233456); enabled.setChecked(HealthConnectBridge.isEnabled(this)); connection.addView(enabled);
        enabled.setOnCheckedChangeListener((button, checked) -> {
            HealthConnectBridge.setEnabled(this, checked);
            if (checked) {
                if (HealthConnectBridge.status(this).optJSONArray("readableKinds").length() < 3)
                    HealthConnectBridge.requestPermissions(this, false, false);
                else CloudSync.requestActivity(this, true, true);
            }
            render();
        });
        status = label(connection, "", 14, 0xff66789a, false);
        button(connection, "授权运动、心率与步数", () -> {
            if (!enabled.isChecked()) enabled.setChecked(true);
            else HealthConnectBridge.requestPermissions(this, false, false);
            render();
        });
        background = button(connection, "授权后台读取", () -> HealthConnectBridge.requestPermissions(this, true, false));
        sync = button(connection, "同步最近 48 小时", () -> {
            CloudSync.requestActivity(this, true, true); render();
        });
        upload = label(connection, "", 13, 0xff66789a, false);

        LinearLayout source = card(page);
        label(source, "先连接数据来源", 18, 0xff233456, true);
        label(source, "请在小米运动健康中启用 Health Connect 数据共享，并在系统中允许它写入运动、心率和步数。" +
                "血糖镜像只读取来源为小米运动健康的记录。", 14, 0xff66789a, false);
        button(source, "打开小米运动健康", () -> {
            Intent launch = getPackageManager().getLaunchIntentForPackage(HealthPolicy.ORIGIN);
            if (launch == null) Toast.makeText(this, "没有找到官方小米运动健康。", Toast.LENGTH_SHORT).show();
            else startActivity(launch);
        });
        button(source, "打开 Health Connect 设置", () -> HealthConnectBridge.openSettings(this));
        label(source, "空白时段代表没有可读数据，不能据此判断未运动。心率可能只在运动期间共享，步数也可能为较长时段汇总。", 13, 0xff66789a, false);

        LinearLayout policy = card(page);
        label(policy, "数据用途与隐私", 18, 0xff233456, true);
        label(policy, "经你授权后，读取运动起止时间与类型、心率采样、步数区间，以及记录来源和设备信息。" +
                "不读取位置或运动路线，不修改健康记录。\n\n" +
                "启用云同步后，这些记录会通过当前云连接上传到你的 Ali 服务器，与血糖按时间对齐，" +
                "用于统计及 AI 辅助观察；必要的运动摘要会随分析请求提供给已配置的模型服务。" +
                "不能仅凭时间相关性认定运动导致某次血糖变化。\n\n" +
                "可以随时关闭此功能或在系统 Health Connect 撤销权限，后续读取将停止；" +
                "撤销权限不自动删除已上传的历史数据。当前只同步最近 48 小时，不申请更早历史读取。", 14, 0xff66789a, false);
        button(page, "返回", this::finish);
    }

    private LinearLayout card(LinearLayout parent) {
        return MobileStyle.card(parent);
    }
    private TextView label(LinearLayout parent, String value, int size, int color, boolean bold) {
        return MobileStyle.text(parent, value, size, color, bold);
    }
    private Button button(LinearLayout parent, String value, Runnable action) {
        return MobileStyle.button(parent, value, action);
    }
    private void render() {
        if (status == null) return;
        status.setText(HealthConnectBridge.statusText(this));
        boolean available = HealthConnectBridge.available(this), enabled = HealthConnectBridge.isEnabled(this);
        background.setEnabled(available && enabled && HealthConnectBridge.extendedReadsSupported() && !HealthConnectBridge.canReadInBackground(this));
        background.setText(HealthConnectBridge.canReadInBackground(this) ? "后台读取已授权" : "授权后台读取（可选）");
        sync.setEnabled(available && enabled && HealthConnectBridge.hasReadPermissions(this));
        upload.setText(CloudSync.activityStatus(this));
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results); render();
        if (request == HealthConnectBridge.REQUEST_PERMISSIONS && HealthConnectBridge.isEnabled(this)
                && HealthConnectBridge.hasReadPermissions(this)) CloudSync.requestActivity(this, true, true);
    }
    @Override public void onResume() { super.onResume(); handler.removeCallbacks(refresh); handler.post(refresh); }
    @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
