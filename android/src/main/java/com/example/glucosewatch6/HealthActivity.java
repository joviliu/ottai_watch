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
    private TextView status, upload, phoneStatus;
    private Button background, sync, phoneGrant, phoneSync;
    private final Runnable refresh = new Runnable() {
        public void run() { render(); handler.postDelayed(this, 3000); }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout page = MobileStyle.page(this);
        label(page, "运动与血糖", 28, 0xff233456, true);
        label(page, "结合锻炼、睡眠、心率、步数和活动热量，与血糖对齐观察。", 15, 0xff66789a, false);

        LinearLayout connection = card(page);
        Switch enabled = new Switch(this); enabled.setText("启用 Health Connect 活动与睡眠"); enabled.setTextSize(17);
        enabled.setTextColor(0xff233456); enabled.setChecked(HealthConnectBridge.isEnabled(this)); connection.addView(enabled);
        enabled.setOnCheckedChangeListener((button, checked) -> {
            HealthConnectBridge.setEnabled(this, checked);
            if (checked) {
                if (HealthConnectBridge.status(this).optJSONArray("readableKinds").length() < 5)
                    HealthConnectBridge.requestPermissions(this, false, false);
                else CloudSync.requestActivity(this, true, true);
            }
            render();
        });
        status = label(connection, "", 14, 0xff66789a, false);
        button(connection, "授权锻炼、心率、步数、热量与睡眠", () -> {
            if (!enabled.isChecked()) enabled.setChecked(true);
            else HealthConnectBridge.requestPermissions(this, false, false);
            render();
        });
        background = button(connection, "授权后台读取", () -> HealthConnectBridge.requestPermissions(this, true, false));
        sync = button(connection, "同步最近 48 小时", () -> {
            CloudSync.requestActivity(this, true, true); render();
        });
        upload = label(connection, "", 13, 0xff66789a, false);

        LinearLayout phone = card(page);
        label(phone, "手机步数补充", 18, 0xff233456, true);
        label(phone, "从小米手机现有的系统计步记录读取步数，可与 Health Connect 心率同时使用。" +
                "不需要额外运动应用，也不启动新的传感器采集。", 14, 0xff66789a, false);
        Switch phoneEnabled = new Switch(this); phoneEnabled.setText("启用手机步数"); phoneEnabled.setTextSize(17);
        phoneEnabled.setTextColor(0xff233456); phoneEnabled.setChecked(PhoneStepsBridge.isEnabled(this)); phone.addView(phoneEnabled);
        phoneEnabled.setOnCheckedChangeListener((button, checked) -> {
            PhoneStepsBridge.setEnabled(this, checked);
            if (checked && PhoneStepsBridge.available(this)) {
                if (PhoneStepsBridge.hasPermission(this)) CloudSync.requestActivity(this, true, true);
                else PhoneStepsBridge.requestPermission(this);
            }
            render();
        });
        phoneStatus = label(phone, "", 14, 0xff66789a, false);
        phoneGrant = button(phone, "授权身体活动", () -> {
            if (!phoneEnabled.isChecked()) phoneEnabled.setChecked(true);
            else PhoneStepsBridge.requestPermission(this);
            render();
        });
        phoneSync = button(phone, "同步手机步数（最近 48 小时）", () -> {
            CloudSync.requestActivity(this, true, true); render();
        });
        label(phone, "步数来自本机，而非手表。手机未随身携带时记录可能不完整；缺少记录不代表没有活动。", 13, 0xff66789a, false);

        LinearLayout source = card(page);
        label(source, "Health Connect 数据来源", 18, 0xff233456, true);
        label(source, "请在小米运动健康中启用 Health Connect 数据共享，并在系统中允许它写入锻炼、睡眠、心率、步数和活动热量。" +
                "此通道只读取来源为小米运动健康的记录，手机步数通道可独立启用。", 14, 0xff66789a, false);
        button(source, "打开小米运动健康", () -> {
            Intent launch = getPackageManager().getLaunchIntentForPackage(HealthPolicy.ORIGIN);
            if (launch == null) Toast.makeText(this, "没有找到官方小米运动健康。", Toast.LENGTH_SHORT).show();
            else startActivity(launch);
        });
        button(source, "打开 Health Connect 设置", () -> HealthConnectBridge.openSettings(this));
        label(source, "空白时段代表没有可读数据，不能据此判断未运动。睡眠和锻炼按原始记录区间标记，睡眠区间可能包含清醒时间；不读取睡眠阶段。步数可能为较长时段汇总。" +
                "活动热量是设备或应用提供的估计值，以 kcal 展示，不包含基础代谢；来源设备以原记录为准。", 13, 0xff66789a, false);

        LinearLayout policy = card(page);
        label(policy, "数据用途与隐私", 18, 0xff233456, true);
        label(policy, "经你授权后，读取锻炼起止时间与类型、睡眠记录区间、心率采样、步数区间、估计活动热量，以及记录来源和设备信息。" +
                "不读取睡眠阶段、标题或备注，不读取位置或运动路线，不修改健康记录。\n\n" +
                "启用云同步后，这些记录会通过当前云连接上传到你的 Ali 服务器，与血糖按时间对齐，" +
                "用于统计及 AI 辅助观察；必要的运动摘要会随分析请求提供给已配置的模型服务。" +
                "不能仅凭时间相关性认定运动导致某次血糖变化。\n\n" +
                "两个数据通道可独立关闭。也可以在系统 Health Connect 撤销健康读取权限，" +
                "或在应用权限中撤销手机计步的“身体活动”权限，相应读取将停止；" +
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
        phoneStatus.setText(PhoneStepsBridge.statusText(this));
        boolean phoneAvailable = PhoneStepsBridge.available(this), phoneEnabled = PhoneStepsBridge.isEnabled(this);
        phoneGrant.setEnabled(phoneAvailable && !PhoneStepsBridge.hasPermission(this));
        phoneGrant.setText(PhoneStepsBridge.hasPermission(this) ? "身体活动已授权" : "授权身体活动");
        phoneSync.setEnabled(phoneAvailable && phoneEnabled && PhoneStepsBridge.hasPermission(this));
        upload.setText(CloudSync.activityStatus(this));
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results); render();
        if (request == HealthConnectBridge.REQUEST_PERMISSIONS && HealthConnectBridge.isEnabled(this)
                && HealthConnectBridge.hasReadPermissions(this)) CloudSync.requestActivity(this, true, true);
        if (request == PhoneStepsBridge.REQUEST_PERMISSION && PhoneStepsBridge.isEnabled(this)
                && PhoneStepsBridge.hasPermission(this)) CloudSync.requestActivity(this, true, true);
    }
    @Override public void onResume() { super.onResume(); handler.removeCallbacks(refresh); handler.post(refresh); }
    @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
