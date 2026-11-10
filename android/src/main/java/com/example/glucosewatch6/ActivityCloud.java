package com.example.glucosewatch6;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.AtomicFile;
import java.io.*;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONArray;
import org.json.JSONObject;

/** Optional independent, bounded activity snapshot channel. No sensors or wake locks. */
final class ActivityCloud {
    private static ActivityCloud healthInstance, phoneInstance;
    private final Context context;
    private final boolean phone;
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(4));
    private final AtomicBoolean busy = new AtomicBoolean();
    private final AtomicFile pending;
    private volatile long generation;

    private ActivityCloud(Context c, boolean phone) {
        context=c.getApplicationContext();this.phone=phone;
        pending=new AtomicFile(new File(context.getFilesDir(), phone?"phone-steps-outbox.json":"health-connect-outbox.json"));
    }
    private static synchronized ActivityCloud get(Context c, boolean phone) {
        if(phone) { if(phoneInstance==null)phoneInstance=new ActivityCloud(c,true);return phoneInstance; }
        if(healthInstance==null)healthInstance=new ActivityCloud(c,false);return healthInstance;
    }
    static String status(Context c) {
        String text="";
        if(HealthConnectBridge.isEnabled(c)) text="小米共享："+get(c,false).prefs().getString("activityStatus","尚未同步");
        if(PhoneStepsBridge.isEnabled(c)) text+=(text.isEmpty()?"":"\n")+"手机计步："+get(c,true).prefs().getString("activityStatus","尚未同步");
        return text.isEmpty()?"活动同步尚未启用":text;
    }
    static void request(Context c, boolean foreground, boolean force) {
        get(c,false).request(foreground,force);get(c,true).request(foreground,force);
    }
    static void configured(Context c) {
        get(c,false).reset();get(c,true).reset();
    }
    private void reset() {
        ActivityCloud cloud=this;
        cloud.generation++;
        cloud.submit(() -> {
            cloud.pending.delete();
            cloud.prefs().edit().remove("activityAttempt").remove("activityNextAttempt")
                .remove("activityPermanent").remove("activityFailures").apply();
            cloud.request(false,true);
        });
    }
    private SharedPreferences prefs() { return phone?context.getSharedPreferences("phone_activity_cloud",0):CloudConfig.prefs(context); }
    private void status(String value) { prefs().edit().putString("activityStatus",value).apply(); }
    private boolean enabled() { return phone?PhoneStepsBridge.isEnabled(context):HealthConnectBridge.isEnabled(context); }
    private boolean hasPermission() { return phone?PhoneStepsBridge.hasPermission(context):HealthConnectBridge.hasReadPermissions(context); }
    private String source() { return phone?"phone_steps":"health_connect"; }
    private void submit(Runnable task) {
        try { worker.execute(task); }
        catch(RejectedExecutionException error) { busy.set(false); status("活动同步忙，稍后重试"); }
    }
    private void request(boolean foreground, boolean force) {
        if(!enabled()) return;
        if(!CloudConfig.configured(context)) { status("请先配置云同步，再上传活动资料"); return; }
        long now=System.currentTimeMillis();
        if(!force && (prefs().getBoolean("activityPermanent",false)
                || now < prefs().getLong("activityNextAttempt",0))) return;
        if(!force && !pending.getBaseFile().exists()
                && !ActivitySyncPolicy.due(now,prefs().getLong("activityAttempt",0),false)) return;
        if(!busy.compareAndSet(false,true)) return;
        final long expected=generation;
        final String endpoint=CloudConfig.endpoint(context);
        submit(() -> {
            try {
                if(force) prefs().edit().putInt("activityFailures",0).putBoolean("activityPermanent",false)
                    .putLong("activityNextAttempt",0).apply();
                if(pending.getBaseFile().exists()) {
                    JSONObject envelope=null;
                    try { envelope=readPending(); }
                    catch(Exception invalidCache) { pending.delete(); }
                    if(envelope!=null) {
                        JSONObject snapshot=envelope.optJSONObject("snapshot");
                        if(snapshot!=null && source().equals(snapshot.optString("source"))
                                && endpoint.equals(envelope.optString("endpoint")) && permissionsStillGranted(snapshot))
                            upload(snapshot,endpoint,expected);
                    }
                    pending.delete();
                }
                if(!ActivitySyncPolicy.due(System.currentTimeMillis(),prefs().getLong("activityAttempt",0),force)) {
                    busy.set(false); return;
                }
                prefs().edit().putLong("activityAttempt",System.currentTimeMillis()).apply();
                if(!hasPermission()) {
                    JSONObject snapshot=new JSONObject().put("source",source()).put("status","permission_denied")
                        .put("syncedAt",System.currentTimeMillis()).put("windowStart",System.currentTimeMillis()-HealthPolicy.WINDOW_MILLIS)
                        .put("windowEnd",System.currentTimeMillis()).put("readableKinds",new JSONArray()).put("records",new JSONArray());
                    savePending(snapshot,endpoint); upload(snapshot,endpoint,expected); pending.delete();
                    status("尚未授予活动读取权限；云端保留已有历史"); busy.set(false); return;
                }
                status(phone?"正在读取手机系统计步区间…":"正在读取小米运动健康已共享的活动记录…");
                HealthConnectBridge.Callback callback=new HealthConnectBridge.Callback() {
                    public void onSuccess(JSONObject snapshot) {
                        submit(() -> {
                            try {
                                if(expected!=generation || !endpoint.equals(CloudConfig.endpoint(context))
                                        || !enabled() || !source().equals(snapshot.optString("source"))) return;
                                savePending(snapshot,endpoint); upload(snapshot,endpoint,expected); pending.delete();
                            } catch(Exception error) { failed(error); }
                            finally { busy.set(false); }
                        });
                    }
                    public void onError(String code,String message) {
                        status(message); busy.set(false);
                    }
                };
                if(phone)PhoneStepsBridge.collectRecent(context,callback);
                else HealthConnectBridge.collectRecent(context,foreground,callback);
            } catch(Exception error) { failed(error); busy.set(false); }
        });
    }
    private void savePending(JSONObject snapshot,String endpoint) throws Exception {
        byte[] bytes=new JSONObject().put("endpoint",endpoint).put("snapshot",snapshot).toString().getBytes(StandardCharsets.UTF_8);
        if(bytes.length>ActivitySyncPolicy.MAX_BODY+2048) throw new IOException("Bound exceeded");
        FileOutputStream stream=null;
        try {
            stream=pending.startWrite(); stream.write(bytes); pending.finishWrite(stream);
        } catch(Exception error) { if(stream!=null)pending.failWrite(stream);throw error; }
    }
    private JSONObject readPending() throws Exception {
        try(InputStream input=pending.openRead();ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
            byte[] buffer=new byte[8192];int n;
            while((n=input.read(buffer))!=-1) {
                if(bytes.size()+n>ActivitySyncPolicy.MAX_BODY+2048) throw new IOException("Bound exceeded");
                bytes.write(buffer,0,n);
            }
            return new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
        }
    }
    private void upload(JSONObject snapshot,String endpoint,long expected) throws Exception {
        if(expected!=generation || !enabled()) return;
        if(!permissionsStillGranted(snapshot))throw new SecurityException("Permissions changed");
        CloudConfig.Connection credentials=CloudConfig.connection(context);
        if(!endpoint.equals(credentials.endpoint))throw new IOException("Configuration changed");
        byte[] bytes=snapshot.toString().getBytes(StandardCharsets.UTF_8);
        if(bytes.length>ActivitySyncPolicy.MAX_BODY)throw new IOException("Bound exceeded");
        javax.net.ssl.HttpsURLConnection connection=(javax.net.ssl.HttpsURLConnection)new URL(endpoint+"/api/v1/activity").openConnection();
        try {
            connection.setConnectTimeout(10000);connection.setReadTimeout(15000);connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("POST");connection.setRequestProperty("Authorization","Bearer "+credentials.token);
            connection.setRequestProperty("Content-Type","application/json");connection.setRequestProperty("Accept","application/json");
            connection.setDoOutput(true);connection.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream output=connection.getOutputStream()) { output.write(bytes); }
            int code=connection.getResponseCode();
            if(code<200 || code>=300)throw new ActivityHttpFailure(code);
            try(InputStream input=connection.getInputStream();ByteArrayOutputStream response=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[4096];int n;
                while((n=input.read(buffer))!=-1) {
                    if(response.size()+n>65536)throw new IOException("Response bound");response.write(buffer,0,n);
                }
                JSONObject reply=new JSONObject(new String(response.toByteArray(),StandardCharsets.UTF_8));
                String state=reply.optString("status");
                if(!reply.optBoolean("ok") || !(state.equals("accepted") || state.equals("duplicate") || state.equals("stale_ignored")))
                    throw new IOException("Invalid acknowledgement");
            }
            if(expected!=generation) return;
            prefs().edit().putLong("activityLastUpload",System.currentTimeMillis()).putInt("activityFailures",0)
                .putLong("activityNextAttempt",0).putBoolean("activityPermanent",false).apply();
            int count=snapshot.optJSONArray("records")==null?0:snapshot.getJSONArray("records").length();
            status(count>0 ? "活动资料已同步，"+count+" 条来源记录" : phone
                ? "已同步；手机系统暂未提供计步记录" : "已同步；小米运动健康尚未共享可读记录");
        } finally { connection.disconnect(); }
    }
    private boolean permissionsStillGranted(JSONObject snapshot) {
        if(!"available".equals(snapshot.optString("status")))return true;
        if(phone)return PhoneStepsBridge.hasPermission(context);
        JSONArray previous=snapshot.optJSONArray("readableKinds");
        JSONArray current=HealthConnectBridge.status(context).optJSONArray("readableKinds");
        if(previous==null || current==null)return false;
        for(int i=0;i<previous.length();i++) {
            boolean found=false;
            for(int j=0;j<current.length();j++)if(previous.optString(i).equals(current.optString(j)))found=true;
            if(!found)return false;
        }
        return true;
    }
    private void failed(Exception error) {
        // No exception text, record values, URLs or credentials in logs.
        android.util.Log.w("OttaiActivity","exception="+error.getClass().getSimpleName());
        int count=prefs().getInt("activityFailures",0)+1;
        boolean permanent=error instanceof ActivityHttpFailure && CloudPolicy.permanent(((ActivityHttpFailure)error).code);
        prefs().edit().putInt("activityFailures",count).putBoolean("activityPermanent",permanent)
            .putLong("activityNextAttempt",System.currentTimeMillis()+ActivitySyncPolicy.delay(count)).apply();
        status(permanent ? "活动上传被拒绝，请检查配置后手动同步；血糖同步不受影响"
            : "活动上传暂未完成，完整记录已保留，稍后重试");
    }
    private static final class ActivityHttpFailure extends IOException {
        final int code;ActivityHttpFailure(int code){this.code=code;}
    }
}
