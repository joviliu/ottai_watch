package com.example.glucosewatch6;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.health.connect.HealthConnectException;
import android.health.connect.HealthConnectManager;
import android.health.connect.ReadRecordsRequestUsingFilters;
import android.health.connect.ReadRecordsResponse;
import android.health.connect.TimeInstantRangeFilter;
import android.health.connect.datatypes.DataOrigin;
import android.health.connect.datatypes.Device;
import android.health.connect.datatypes.ExerciseSessionRecord;
import android.health.connect.datatypes.HeartRateRecord;
import android.health.connect.datatypes.IntervalRecord;
import android.health.connect.datatypes.Metadata;
import android.health.connect.datatypes.StepsRecord;
import android.os.Build;
import android.os.Bundle;
import android.os.OutcomeReceiver;
import android.os.ext.SdkExtensions;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/** Read-only platform Health Connect access (Android 14+), isolated from BLE/glucose work. */
public final class HealthConnectBridge {
    private HealthConnectBridge() { }
    public static final int REQUEST_PERMISSIONS = 320;
    public static final String READ_HEART_RATE = "android.permission.health.READ_HEART_RATE";
    public static final String READ_STEPS = "android.permission.health.READ_STEPS";
    public static final String READ_EXERCISE = "android.permission.health.READ_EXERCISE";
    public static final String READ_BACKGROUND = "android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND";
    public static final String READ_HISTORY = "android.permission.health.READ_HEALTH_DATA_HISTORY";
    private static final String[] KINDS = {"exercise", "heart_rate", "steps"};
    private static final String[] PERMISSIONS = {READ_EXERCISE, READ_HEART_RATE, READ_STEPS};
    private static final AtomicBoolean INSTALLED = new AtomicBoolean(), ACTIVE = new AtomicBoolean();
    private static final AtomicInteger VISIBLE = new AtomicInteger();
    private static final AtomicLong VISIBILITY_EPOCH = new AtomicLong();
    private static final ScheduledThreadPoolExecutor WORKER = new ScheduledThreadPoolExecutor(1, task -> {
        Thread thread = new Thread(task, "ottai-health-connect");
        thread.setDaemon(true); thread.setPriority(Thread.MIN_PRIORITY); return thread;
    });
    static { WORKER.setRemoveOnCancelPolicy(true); }

    public interface Callback {
        /** Only called after every page/type succeeds. Runs on the dedicated health executor. */
        void onSuccess(JSONObject completeSnapshot);
        /** No partial snapshot is emitted; previously uploaded health history must be retained. */
        void onError(String code, String userMessage);
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences("health_connect", Context.MODE_PRIVATE);
    }
    public static boolean isEnabled(Context context) { return prefs(context).getBoolean("enabled", false); }
    public static void setEnabled(Context context, boolean enabled) { prefs(context).edit().putBoolean("enabled", enabled).apply(); }

    /** Install once in Application.onCreate, before any Activity starts. */
    public static void install(Context context) {
        Context app = context.getApplicationContext();
        if (!(app instanceof Application) || !INSTALLED.compareAndSet(false, true)) return;
        ((Application) app).registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks() {
            public void onActivityStarted(Activity a) { VISIBLE.incrementAndGet(); }
            public void onActivityStopped(Activity a) {
                if (VISIBLE.updateAndGet(n -> Math.max(0, n - 1)) == 0) VISIBILITY_EPOCH.incrementAndGet();
            }
            public void onActivityCreated(Activity a, Bundle b) { }
            public void onActivityResumed(Activity a) { }
            public void onActivityPaused(Activity a) { }
            public void onActivitySaveInstanceState(Activity a, Bundle b) { }
            public void onActivityDestroyed(Activity a) { }
        });
    }

    public static boolean available(Context context) {
        if (Build.VERSION.SDK_INT < 34) return false;
        try { return context.getSystemService("healthconnect") != null; }
        catch (RuntimeException error) { return false; }
    }
    private static boolean granted(Context context, String permission) {
        return available(context) && context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
    }
    public static boolean extendedReadsSupported() {
        if (Build.VERSION.SDK_INT < 34) return false;
        // Same minimum version as the official AndroidX feature map (U extension 13):
        // https://android.googlesource.com/platform/frameworks/support/+/androidx-main/health/connect/connect-client/src/main/java/androidx/health/connect/client/HealthConnectFeatures.kt
        try { return HealthPolicy.supportsExtendedReads(Build.VERSION.SDK_INT, SdkExtensions.getExtensionVersion(34)); }
        catch (RuntimeException error) { return false; }
    }
    public static boolean canReadInBackground(Context context) {
        return extendedReadsSupported() && granted(context, READ_BACKGROUND);
    }
    public static boolean hasReadPermissions(Context context) {
        for (String permission : PERMISSIONS) if (granted(context, permission)) return true;
        return false;
    }

    /** Explicit user action only. Android's permission controller owns the grant flow. */
    public static void requestPermissions(Activity activity, boolean includeBackground, boolean includeHistory) {
        if (!available(activity)) return;
        List<String> requested = new ArrayList<>();
        if (!includeBackground && !includeHistory) {
            for (String permission : PERMISSIONS) if (!granted(activity, permission)) requested.add(permission);
        } else if (extendedReadsSupported()) {
            if (includeBackground && !granted(activity, READ_BACKGROUND)) requested.add(READ_BACKGROUND);
            if (includeHistory && !granted(activity, READ_HISTORY)) requested.add(READ_HISTORY);
        }
        if (!requested.isEmpty()) activity.requestPermissions(requested.toArray(new String[0]), REQUEST_PERMISSIONS);
    }

    public static void openSettings(Context context) {
        if (Build.VERSION.SDK_INT < 34) return;
        Intent intent = new Intent("android.health.connect.action.HEALTH_HOME_SETTINGS").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try { context.startActivity(intent); }
        catch (RuntimeException missingHome) {
            try { context.startActivity(new Intent(HealthConnectManager.ACTION_MANAGE_HEALTH_PERMISSIONS)
                    .putExtra(Intent.EXTRA_PACKAGE_NAME, context.getPackageName()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); }
            catch (RuntimeException ignored) { }
        }
    }

    public static JSONObject status(Context context) {
        JSONObject value = new JSONObject();
        try {
            JSONArray kinds = new JSONArray();
            for (int i = 0; i < KINDS.length; i++) if (granted(context, PERMISSIONS[i])) kinds.put(KINDS[i]);
            SharedPreferences p = prefs(context);
            value.put("enabled", isEnabled(context)).put("platformAvailable", available(context))
                    .put("readableKinds", kinds).put("backgroundSupported", extendedReadsSupported())
                    .put("backgroundGranted", canReadInBackground(context)).put("historySupported", extendedReadsSupported())
                    .put("historyGranted", extendedReadsSupported() && granted(context, READ_HISTORY))
                    .put("lastReadAt", p.getLong("lastReadAt", 0)).put("recordCount", p.getInt("recordCount", 0))
                    .put("sampleCount", p.getInt("sampleCount", 0)).put("lastError", p.getString("lastError", ""));
        } catch (Exception ignored) { }
        return value;
    }

    public static String statusText(Context context) {
        if (!available(context)) return "此手机暂不支持平台 Health Connect（需 Android 14 或更新版本）。";
        if (!isEnabled(context)) return "运动辅助分析尚未启用。";
        StringBuilder text = new StringBuilder("只读取小米运动健康写入的数据\n");
        for (int i = 0; i < KINDS.length; i++) text.append(new String[]{"运动", "心率", "步数"}[i])
                .append(granted(context, PERMISSIONS[i]) ? "：已授权  " : "：未授权  ");
        text.append("\n").append(canReadInBackground(context) ? "后台读取：已授权" : extendedReadsSupported()
                ? "后台读取：未授权；仅应用在前台时读取" : "后台读取：系统版本暂不支持；仅前台读取");
        text.append("\n更早历史：").append(extendedReadsSupported() && granted(context, READ_HISTORY)
                ? "已授权；当前同步最近 48 小时" : "当前仅同步最近 48 小时，不需要更早历史权限");
        SharedPreferences p = prefs(context);
        if (p.getLong("lastReadAt", 0) > 0) text.append("\n上次完整读取 ").append(p.getInt("recordCount", 0))
                .append(" 条记录、").append(p.getInt("sampleCount", 0)).append(" 个心率采样");
        String error = p.getString("lastError", "");
        if (!error.isEmpty()) text.append("\n").append(error);
        return text.toString();
    }

    /** Complete 48h record-start window; original intervals and sample timestamps are preserved. */
    public static void collectRecent(Context context, boolean foreground, Callback callback) {
        final Context app = context.getApplicationContext();
        install(app);
        if (!ACTIVE.compareAndSet(false, true)) {
            // Do not enqueue repeat requests while a scan is active. Busy is reported on the caller.
            callback.onError("busy", "运动数据正在读取，请稍后重试。"); return;
        }
        WORKER.execute(() -> {
            if (!isEnabled(app)) { failBeforeScan(app, callback, "disabled", "运动辅助分析尚未启用。"); return; }
            if (!available(app)) { failBeforeScan(app, callback, "unavailable", "系统 Health Connect 暂不可用。"); return; }
            if (!hasReadPermissions(app)) { failBeforeScan(app, callback, "permission_denied", "请先授权读取运动、心率或步数。"); return; }
            if (!canReadInBackground(app) && (!foreground || VISIBLE.get() == 0)) {
                failBeforeScan(app, callback, "foreground_only", "后台读取未授权，请在运动数据页面保持应用打开后同步。"); return;
            }
            try { new Scan(app, callback).start(); }
            catch (Exception error) { failBeforeScan(app, callback, "read_failed", "运动数据读取失败；已有历史保留，请稍后重试。"); }
        });
    }
    private static void failBeforeScan(Context context, Callback callback, String code, String message) {
        ACTIVE.set(false); prefs(context).edit().putString("lastError", message).apply(); callback.onError(code, message);
    }

    /** Kept in a nested class so Android <34 can load the app without resolving HC record types. */
    private static final class Scan {
        final Context context; final Callback callback; final HealthConnectManager manager;
        final long end = System.currentTimeMillis(), start = end - HealthPolicy.WINDOW_MILLIS;
        final long visibilityEpoch = VISIBILITY_EPOCH.get();
        final JSONArray records = new JSONArray(), readable = new JSONArray();
        final List<Integer> kinds = new ArrayList<>(); final HealthPolicy.Budget budget = new HealthPolicy.Budget();
        ScheduledFuture<?> deadline; boolean finished; int kindIndex;

        Scan(Context context, Callback callback) {
            this.context = context; this.callback = callback;
            manager = (HealthConnectManager) context.getSystemService("healthconnect");
            for (int i = 0; i < KINDS.length; i++) if (granted(context, PERMISSIONS[i])) { kinds.add(i); readable.put(KINDS[i]); }
        }
        void start() {
            deadline = WORKER.schedule(() -> fail("timeout", "运动数据读取超时；未上传不完整数据，请稍后重试。"), HealthPolicy.TIMEOUT_MILLIS, TimeUnit.MILLISECONDS);
            readKind();
        }
        void checkAccess() {
            if (!isEnabled(context)) throw new SecurityException("disabled");
            for (int kind : kinds) if (!granted(context, PERMISSIONS[kind])) throw new SecurityException("revoked");
            if (!canReadInBackground(context) && (VISIBLE.get() == 0 || VISIBILITY_EPOCH.get() != visibilityEpoch))
                throw new SecurityException("foreground_lost");
        }
        void readKind() {
            if (finished) return;
            try {
                checkAccess(); budget.nextKind();
                if (kindIndex == kinds.size()) { complete(); return; }
                int kind = kinds.get(kindIndex);
                if (kind == 0) readPage(ExerciseSessionRecord.class, -1);
                else if (kind == 1) readPage(HeartRateRecord.class, -1);
                else readPage(StepsRecord.class, -1);
            } catch (Exception error) { failed(error); }
        }
        <T extends IntervalRecord> void readPage(Class<T> type, long token) {
            if (finished) return;
            try {
                checkAccess(); budget.page(token);
                // Raw readRecords selects records whose START falls in [start,end), not all
                // intervals overlapping it. Server snapshot reconciliation must use the same scope.
                // AOSP RecordHelper#getReadTableRequestWhereClause (start_time >= start, < end):
                // https://android.googlesource.com/platform/packages/modules/HealthFitness/+/refs/heads/main/service/java/com/android/server/healthconnect/storage/datatypehelpers/RecordHelper.java
                ReadRecordsRequestUsingFilters.Builder<T> request = new ReadRecordsRequestUsingFilters.Builder<>(type)
                        .addDataOrigins(new DataOrigin.Builder().setPackageName(HealthPolicy.ORIGIN).build())
                        .setTimeRangeFilter(new TimeInstantRangeFilter.Builder().setStartTime(Instant.ofEpochMilli(start))
                                .setEndTime(Instant.ofEpochMilli(end)).build()).setPageSize(500);
                if (token != -1) request.setPageToken(token); else request.setAscending(true);
                manager.readRecords(request.build(), WORKER, new OutcomeReceiver<ReadRecordsResponse<T>, HealthConnectException>() {
                    public void onResult(ReadRecordsResponse<T> result) {
                        if (finished) return;
                        try {
                            checkAccess();
                            for (T record : result.getRecords()) append(record);
                            long next = result.getNextPageToken();
                            if (next == -1) { kindIndex++; readKind(); } else readPage(type, next);
                        } catch (Exception error) { failed(error); }
                    }
                    public void onError(HealthConnectException error) { if (!finished) failed(error); }
                });
            } catch (Exception error) { failed(error); }
        }
        void append(IntervalRecord record) throws Exception {
            Metadata metadata = record.getMetadata();
            if (!HealthPolicy.ORIGIN.equals(metadata.getDataOrigin().getPackageName())) throw new SecurityException("unexpected_origin");
            String kind = record instanceof ExerciseSessionRecord ? "exercise" : record instanceof HeartRateRecord ? "heart_rate" : "steps";
            JSONObject value = new JSONObject().put("id", metadata.getId()).put("kind", kind).put("origin", HealthPolicy.ORIGIN)
                    .put("startAt", record.getStartTime().toEpochMilli()).put("endAt", record.getEndTime().toEpochMilli())
                    .put("modifiedAt", metadata.getLastModifiedTime().toEpochMilli()).put("recordingMethod", metadata.getRecordingMethod());
            if (record.getStartZoneOffset() != null) value.put("startOffsetSeconds", record.getStartZoneOffset().getTotalSeconds());
            if (record.getEndZoneOffset() != null) value.put("endOffsetSeconds", record.getEndZoneOffset().getTotalSeconds());
            Device device = metadata.getDevice();
            if (device != null) value.put("device", new JSONObject().put("manufacturer", device.getManufacturer())
                    .put("model", device.getModel()).put("type", device.getType()));
            int sampleCount = 0;
            if (record instanceof HeartRateRecord) {
                List<HeartRateRecord.HeartRateSample> original = ((HeartRateRecord) record).getSamples();
                sampleCount = original.size();
                if (sampleCount > HealthPolicy.MAX_SAMPLES - budget.sampleCount()) throw new IllegalArgumentException("snapshot_limit");
                // Platform validation checks only min/max time. Its internal representation uses
                // a set, so don't assume ordering/unique times. Sort without discarding conflicts.
                List<HeartRateRecord.HeartRateSample> samples = new ArrayList<>(original);
                samples.sort((a, b) -> {
                    int time = a.getTime().compareTo(b.getTime());
                    return time != 0 ? time : Long.compare(a.getBeatsPerMinute(), b.getBeatsPerMinute());
                });
                JSONArray points = new JSONArray();
                for (HeartRateRecord.HeartRateSample sample : samples) points.put(new JSONObject()
                        .put("time", sample.getTime().toEpochMilli()).put("bpm", sample.getBeatsPerMinute()));
                value.put("samples", points);
            } else if (record instanceof StepsRecord) value.put("count", ((StepsRecord) record).getCount());
            else value.put("exerciseType", ((ExerciseSessionRecord) record).getExerciseType());
            // No notes, title, exercise route/GPS, or invented minute-by-minute step distribution.
            budget.record(kind, metadata.getId(), sampleCount, value.toString().getBytes(StandardCharsets.UTF_8).length);
            records.put(value);
        }
        void complete() throws Exception {
            checkAccess();
            JSONObject snapshot = new JSONObject().put("source", "health_connect").put("status", "available")
                    .put("syncedAt", System.currentTimeMillis()).put("windowStart", start).put("windowEnd", end)
                    .put("readableKinds", readable).put("records", records);
            try {
                PackageInfo origin = context.getPackageManager().getPackageInfo(HealthPolicy.ORIGIN, 0);
                snapshot.put("originApp", new JSONObject().put("packageName", HealthPolicy.ORIGIN)
                        .put("versionName", origin.versionName).put("versionCode", origin.getLongVersionCode()));
            } catch (PackageManager.NameNotFoundException ignored) { }
            if (snapshot.toString().getBytes(StandardCharsets.UTF_8).length > HealthPolicy.MAX_BYTES)
                throw new IllegalArgumentException("snapshot_limit");
            finished = true; deadline.cancel(false); ACTIVE.set(false);
            prefs(context).edit().putLong("lastReadAt", System.currentTimeMillis()).putInt("recordCount", budget.recordCount())
                    .putInt("sampleCount", budget.sampleCount()).putString("lastError", "").apply();
            callback.onSuccess(snapshot);
        }
        void failed(Exception error) {
            if (error instanceof SecurityException || (error instanceof HealthConnectException
                    && ((HealthConnectException) error).getErrorCode() == HealthConnectException.ERROR_SECURITY))
                fail("permission_changed", "读取权限或前台状态发生变化；未上传不完整数据，请返回页面重试。");
            else if (error instanceof IllegalArgumentException)
                fail("snapshot_limit", "运动数据量或分页超出安全上限；未截断、未上传，请稍后重试。");
            else fail("read_failed", "Health Connect 暂时无法读取；已有历史保留，请稍后重试。");
        }
        void fail(String code, String message) {
            if (finished) return;
            finished = true; if (deadline != null) deadline.cancel(false); ACTIVE.set(false);
            prefs(context).edit().putString("lastError", message).apply(); callback.onError(code, message);
        }
    }
}
