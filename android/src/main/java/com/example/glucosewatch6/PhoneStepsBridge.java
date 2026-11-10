package com.example.glucosewatch6;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ProviderInfo;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.CancellationSignal;
import android.os.OperationCanceledException;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Read the phone's existing low-power step database; no sensor listener, service, or wake lock. */
public final class PhoneStepsBridge {
    private PhoneStepsBridge() { }
    public static final String SOURCE = "phone_steps", ORIGIN = "com.miui.rom";
    public static final String AUTHORITY = "com.miui.providers.steps";
    public static final String READ_STEPS = "miui.permission.READ_STEPS";
    public static final String ACTIVITY_RECOGNITION = "android.permission.ACTIVITY_RECOGNITION";
    public static final int REQUEST_PERMISSION = 321;
    private static final Uri URI = Uri.parse("content://" + AUTHORITY + "/item");
    private static final String[] COLUMNS = {"_id", "_begin_time", "_end_time", "_mode", "_steps"};
    private static final AtomicReference<Scan> ACTIVE = new AtomicReference<>();
    private static final ThreadFactory THREADS = task -> {
        Thread thread = new Thread(task, "ottai-phone-steps");
        thread.setDaemon(true); thread.setPriority(Thread.MIN_PRIORITY); return thread;
    };
    private static final ThreadPoolExecutor WORKER = new ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<Runnable>(1), THREADS);
    private static final ScheduledThreadPoolExecutor TIMER = new ScheduledThreadPoolExecutor(1, THREADS);
    static { WORKER.allowCoreThreadTimeOut(true); TIMER.setRemoveOnCancelPolicy(true); }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences("phone_steps", Context.MODE_PRIVATE);
    }
    public static boolean isEnabled(Context context) { return prefs(context).getBoolean("enabled", false); }
    public static void setEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean("enabled", enabled).apply();
        // Independent of Health Connect: retain the watch's heart-rate channel when enabled.
        if (!enabled) {
            Scan scan = ACTIVE.get();
            if (scan != null) TIMER.execute(() -> scan.cancel("disabled", "手机步数同步已关闭；未上传不完整数据。"));
        }
    }
    public static boolean available(Context context) {
        try {
            ProviderInfo provider = context.getPackageManager().resolveContentProvider(AUTHORITY, 0);
            return provider != null && provider.exported && provider.enabled && ORIGIN.equals(provider.packageName);
        } catch (RuntimeException error) { return false; }
    }
    public static boolean hasPermission(Context context) {
        return context.checkSelfPermission(READ_STEPS) == PackageManager.PERMISSION_GRANTED
                && (Build.VERSION.SDK_INT < 29 || context.checkSelfPermission(ACTIVITY_RECOGNITION) == PackageManager.PERMISSION_GRANTED);
    }
    /** Invoke only after an explicit button/toggle action; the system owns the physical-activity prompt. */
    public static void requestPermission(Activity activity) {
        if (Build.VERSION.SDK_INT >= 29 && activity.checkSelfPermission(ACTIVITY_RECOGNITION) != PackageManager.PERMISSION_GRANTED)
            activity.requestPermissions(new String[]{ACTIVITY_RECOGNITION}, REQUEST_PERMISSION);
    }
    public static JSONObject status(Context context) {
        JSONObject result = new JSONObject();
        try {
            SharedPreferences p = prefs(context);
            result.put("source", SOURCE).put("enabled", isEnabled(context)).put("platformAvailable", available(context))
                    .put("readableKinds", hasPermission(context) && available(context) ? new JSONArray().put("steps") : new JSONArray())
                    .put("lastReadAt", p.getLong("lastReadAt", 0)).put("recordCount", p.getInt("recordCount", 0))
                    .put("stepCount", p.getLong("stepCount", 0)).put("lastError", p.getString("lastError", ""));
        } catch (Exception ignored) { }
        return result;
    }
    public static String statusText(Context context) {
        if (!available(context)) return "此手机没有可用的小米系统计步接口；未启动额外传感器采集。";
        if (!isEnabled(context)) return "手机步数尚未启用。";
        if (!hasPermission(context)) return "请允许“身体活动”权限，以读取手机现有步数。";
        SharedPreferences p = prefs(context);
        String result = "手机步数已启用 · 本机系统计步\n只读取原始步数区间，不包含手表心率或运动记录。";
        if (p.getLong("lastReadAt", 0) > 0) result += "\n上次完整读取 " + p.getInt("recordCount", 0) + " 条区间记录";
        String error = p.getString("lastError", "");
        return error.isEmpty() ? result : result + "\n" + error;
    }

    /** Complete 48h START-time snapshot, using the provider's original millisecond intervals. */
    public static void collectRecent(Context context, HealthConnectBridge.Callback callback) {
        Scan scan = new Scan(context.getApplicationContext(), callback);
        if (!ACTIVE.compareAndSet(null, scan)) { callback.onError("busy", "手机步数正在读取，请稍后重试。"); return; }
        try {
            scan.deadline = TIMER.schedule(() -> scan.cancel("timeout", "手机步数读取超时；未上传不完整数据，请稍后重试。"),
                    PhoneStepsPolicy.TIMEOUT_MILLIS, TimeUnit.MILLISECONDS);
            WORKER.execute(scan::read);
        } catch (RejectedExecutionException busy) { scan.fail("busy", "手机步数读取忙，请稍后重试。"); }
    }

    private static final class Row {
        final long id, begin, end, mode, count;
        Row(long id, long begin, long end, long mode, long count) {
            this.id = id; this.begin = begin; this.end = end; this.mode = mode; this.count = count;
        }
    }
    private static final class Scan {
        final Context context; final HealthConnectBridge.Callback callback;
        final CancellationSignal cancellation = new CancellationSignal();
        final AtomicBoolean finished = new AtomicBoolean();
        final long windowEnd = System.currentTimeMillis(), windowStart = windowEnd - PhoneStepsPolicy.WINDOW_MILLIS;
        ScheduledFuture<?> deadline;
        Scan(Context context, HealthConnectBridge.Callback callback) { this.context = context; this.callback = callback; }
        void checkAccess() {
            if (finished.get()) throw new OperationCanceledException();
            if (!isEnabled(context) || !hasPermission(context)) throw new SecurityException();
            cancellation.throwIfCanceled();
        }
        void read() {
            try {
                if (!isEnabled(context)) { fail("disabled", "手机步数尚未启用。"); return; }
                if (!available(context)) { fail("unavailable", "没有可用的小米系统计步接口；已有历史保留。"); return; }
                checkAccess();
                List<Row> rows = new ArrayList<>();
                PhoneStepsPolicy.Budget budget = new PhoneStepsPolicy.Budget();
                // Xiaomi's documented, read-only interface. Original modes/intervals are retained;
                // no daily total is distributed across minutes and no zero rows are invented.
                // https://dev.mi.com/xiaomihyperos/documentation/detail?pId=1603
                try (Cursor cursor = context.getContentResolver().query(URI, COLUMNS,
                        "_begin_time >= ? AND _begin_time < ?", new String[]{Long.toString(windowStart), Long.toString(windowEnd)},
                        "_begin_time ASC, _id ASC", cancellation)) {
                    if (cursor == null) { fail("unavailable", "系统计步没有返回可读结果；已有历史保留。"); return; }
                    int[] columns = new int[COLUMNS.length];
                    for (int i = 0; i < COLUMNS.length; i++) columns[i] = cursor.getColumnIndexOrThrow(COLUMNS[i]);
                    while (cursor.moveToNext()) {
                        checkAccess();
                        for (int column : columns) if (cursor.isNull(column) || cursor.getType(column) != Cursor.FIELD_TYPE_INTEGER)
                            throw new IllegalArgumentException("invalid_phone_steps_field");
                        Row row = new Row(cursor.getLong(columns[0]), cursor.getLong(columns[1]), cursor.getLong(columns[2]),
                                cursor.getLong(columns[3]), cursor.getLong(columns[4]));
                        PhoneStepsPolicy.validate(row.id, row.begin, row.end, row.count, row.mode, windowStart, windowEnd);
                        budget.row(row.id); rows.add(row);
                    }
                }
                checkAccess();
                long collectedAt = System.currentTimeMillis(), stepCount = 0;
                JSONArray records = new JSONArray();
                for (Row row : rows) {
                    JSONObject record = new JSONObject().put("id", "phone-step:" + row.id).put("kind", "steps")
                            .put("origin", ORIGIN).put("startAt", row.begin).put("endAt", row.end)
                            // Provider has no last-modified field. This is an observation revision,
                            // NOT the measurement time; revisionBasis explicitly records that fact.
                            .put("modifiedAt", collectedAt).put("recordingMethod", 0)
                            .put("count", row.count).put("providerMode", row.mode);
                    budget.bytes(record.toString().getBytes(StandardCharsets.UTF_8).length);
                    records.put(record); stepCount += row.count;
                }
                JSONObject snapshot = new JSONObject().put("source", SOURCE).put("status", "available")
                        .put("syncedAt", collectedAt).put("windowStart", windowStart).put("windowEnd", windowEnd)
                        .put("revisionBasis", "collection_time").put("readableKinds", new JSONArray().put("steps")).put("records", records);
                try {
                    PackageInfo origin = context.getPackageManager().getPackageInfo(ORIGIN, 0);
                    snapshot.put("originApp", new JSONObject().put("packageName", ORIGIN).put("versionName", origin.versionName)
                            .put("versionCode", Build.VERSION.SDK_INT >= 28 ? origin.getLongVersionCode() : origin.versionCode));
                } catch (PackageManager.NameNotFoundException ignored) { }
                if (snapshot.toString().getBytes(StandardCharsets.UTF_8).length > PhoneStepsPolicy.MAX_BYTES)
                    throw new IllegalArgumentException("snapshot_limit");
                checkAccess();
                if (!finished.compareAndSet(false, true)) return;
                release();
                prefs(context).edit().putLong("lastReadAt", collectedAt).putInt("recordCount", rows.size())
                        .putLong("stepCount", stepCount).putString("lastError", "").apply();
                callback.onSuccess(snapshot);
            } catch (SecurityException denied) { fail("permission_denied", "手机步数权限或数据来源已变化；已有历史保留。"); }
            catch (OperationCanceledException cancelled) { fail("cancelled", "手机步数读取已取消；已有历史保留。"); }
            catch (IllegalArgumentException invalid) { fail("invalid_snapshot", "手机步数结构或数据超出安全范围；未截断、未上传。"); }
            catch (Exception error) { fail("read_failed", "系统计步暂时无法读取；已有历史保留，请稍后重试。"); }
        }
        void release() { if (deadline != null) deadline.cancel(false); ACTIVE.compareAndSet(this, null); }
        void cancel(String code, String message) { fail(code, message); cancellation.cancel(); }
        void fail(String code, String message) {
            if (!finished.compareAndSet(false, true)) return;
            release(); prefs(context).edit().putString("lastError", message).apply(); callback.onError(code, message);
        }
    }
}
