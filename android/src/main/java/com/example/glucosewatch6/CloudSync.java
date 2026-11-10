package com.example.glucosewatch6;

import android.content.Context;
import android.net.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONArray;
import org.json.JSONObject;

/** Independent of the watch SDK. All disk/network work runs on a bounded single worker. */
final class CloudSync {
    private static CloudSync instance;
    private final Context context;
    private final CloudOutbox outbox;
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(256));
    private final ScheduledThreadPoolExecutor clock = new ScheduledThreadPoolExecutor(1);
    private final AtomicBoolean syncQueued = new AtomicBoolean();
    private final AtomicBoolean networkReady = new AtomicBoolean();
    private ScheduledFuture<?> retry;
    private boolean bootstrapped;
    private long lastDashboard;
    private String stage="idle";
    private CloudSync(Context c) {
        context = c.getApplicationContext(); outbox = new CloudOutbox(context);
        clock.setRemoveOnCancelPolicy(true);
        ConnectivityManager cm = context.getSystemService(ConnectivityManager.class);
        try { cm.registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
            @Override public void onCapabilitiesChanged(Network n, NetworkCapabilities caps) {
                if (caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) && networkReady.compareAndSet(false,true)) submit(() -> {
                    if (!CloudConfig.prefs(context).getBoolean("permanent", false)) {
                        CloudConfig.prefs(context).edit().putInt("failures", 0).putLong("nextAttempt", 0).apply(); request(false);
                    }
                });
            }
            @Override public void onLost(Network n) { networkReady.set(false); }
        }); } catch (RuntimeException ignored) { }
    }
    private static synchronized CloudSync get(Context c) { if (instance == null) instance = new CloudSync(c); return instance; }
    static void accepted(Context c, Reading reading) {
        CloudSync cloud = get(c);
        cloud.submit(() -> {
            try {
                android.content.SharedPreferences prefs=CloudConfig.prefs(cloud.context);
                if (!prefs.getBoolean("permanent",false) && prefs.getInt("failures",0)>=CloudPolicy.MAX_ATTEMPTS
                        && System.currentTimeMillis()>=prefs.getLong("nextAttempt",0)) {
                    prefs.edit().putInt("failures",0).putLong("nextAttempt",0).apply();
                }
                cloud.outbox.enqueue(reading, false); cloud.pending(); cloud.request(false);
            }
            catch (Exception error) { cloud.status("本地上传队列写入失败，请检查存储空间或打开云同步重试"); }
        });
    }
    static void start(Context c) {
        CloudJobService.schedule(c);
        CloudSync cloud = get(c);
        cloud.submit(() -> { cloud.bootstrap(); cloud.request(false); });
    }
    static void retryNow(Context c) {
        CloudSync cloud = get(c);
        cloud.submit(() -> {
            CloudConfig.prefs(cloud.context).edit().putInt("failures", 0).putLong("nextAttempt", 0).putBoolean("permanent", false).apply();
            cloud.bootstrap(); cloud.lastDashboard = 0; cloud.request(true);
        });
    }
    static void configured(Context c, boolean changedEndpoint) {
        CloudJobService.schedule(c);
        ActivityCloud.configured(c);
        CloudSync cloud = get(c);
        cloud.submit(() -> {
            if (changedEndpoint) cloud.outbox.resetHeads();
            cloud.bootstrapped = false;
            CloudConfig.prefs(cloud.context).edit().remove("dashboard").putInt("failures", 0).putLong("nextAttempt", 0).putBoolean("permanent", false).apply();
            cloud.bootstrap(); cloud.lastDashboard = 0; cloud.request(true);
        });
    }
    static String status(Context c) { return CloudConfig.prefs(c).getString("status", "尚未配置云同步"); }
    static void requestActivity(Context c, boolean foreground, boolean force) { ActivityCloud.request(c,foreground,force); }
    static String activityStatus(Context c) { return ActivityCloud.status(c); }
    static void job(Context c, Runnable complete) {
        CloudSync cloud=get(c);
        try { cloud.worker.execute(()-> { try { cloud.bootstrap();cloud.sync(false); } finally { complete.run(); } }); }
        catch(RejectedExecutionException error) { complete.run(); }
    }
    private void submit(Runnable task) {
        try { worker.execute(task); }
        catch (RejectedExecutionException error) { status("上传任务队列已满，本次稍后重试；手表同步不受影响"); }
    }
    private void pending() { CloudConfig.prefs(context).edit().putInt("pending", outbox.count()).apply(); }
    private void status(String message) { CloudConfig.prefs(context).edit().putString("status", message).apply(); }
    private void bootstrap() {
        if (bootstrapped || !CloudConfig.configured(context)) return;
        try {
            String raw = ReadingStore.frame(context);
            if (!raw.isEmpty()) {
                JSONObject current = new JSONObject(raw); long at = current.getLong("sourceAt");
                JSONArray history = current.optJSONArray("history");
                if (history != null) for (int i=0;i<history.length();i++) {
                    JSONObject row=history.getJSONObject(i); long sourceAt=row.getLong("time");
                    if (sourceAt < at) outbox.enqueue(new Reading(row.getDouble("value"), sourceAt, "?"), true);
                }
                // The full latest frame may be a correction saved just before process death.
                outbox.enqueue(new Reading(current.getDouble("value"), at, current.optString("trend", "?")), false);
            }
            bootstrapped = true; pending();
        } catch (Exception error) { status("历史读数回补失败，等待下一条新读数"); }
    }
    private boolean online() {
        ConnectivityManager cm=context.getSystemService(ConnectivityManager.class);
        NetworkCapabilities c=cm.getNetworkCapabilities(cm.getActiveNetwork());
        return c!=null && c.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            && c.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
    }
    private void request(boolean forceDashboard) {
        if (!syncQueued.compareAndSet(false, true)) return;
        try { worker.execute(() -> { try { sync(forceDashboard); } finally { syncQueued.set(false); } }); }
        catch (RejectedExecutionException error) { syncQueued.set(false); status("上传任务队列已满，请稍后重试"); }
    }
    private synchronized void schedule(long delay) {
        if (retry != null) retry.cancel(false);
        retry = clock.schedule(() -> request(false), Math.max(1000, delay), TimeUnit.MILLISECONDS);
    }
    private void sync(boolean forceDashboard) {
        // Separate queue/executor: optional health reads never delay glucose/watch delivery.
        ActivityCloud.request(context,false,false);
        if (!CloudConfig.configured(context)) { status("云同步未配置；读数继续保存在本机待上传队列"); return; }
        android.content.SharedPreferences prefs=CloudConfig.prefs(context);
        if (prefs.getBoolean("permanent",false)) return;
        int failures=prefs.getInt("failures",0);
        if (failures>=CloudPolicy.MAX_ATTEMPTS) { status("云同步连续失败，已暂停；网络恢复、冷却后的新读数或点击立即同步后继续"); return; }
        long wait=prefs.getLong("nextAttempt",0)-System.currentTimeMillis();
        if (wait>0) { schedule(wait); return; }
        if (!online()) { status("当前离线，读数已进入待上传队列"); schedule(900000); return; }
        try {
            stage="queue_read";
            CloudOutbox.Batch batch=outbox.batch();
            if (!batch.ids.isEmpty()) {
                stage="upload_payload";
                String reply=http("POST", "/api/v1/readings", new JSONObject().put("readings",batch.readings).toString());
                stage="upload_decode";
                JSONObject response=new JSONObject(reply);
                stage="upload_ack";
                if (response.optInt("accepted",-1)!=batch.ids.size()) throw new IOException("Batch not acknowledged");
                stage="queue_ack";
                outbox.acknowledged(batch); pending();
                prefs.edit().putLong("lastUpload",System.currentTimeMillis()).putInt("failures",0).putLong("nextAttempt",0).apply();
            }
            if (forceDashboard || !batch.ids.isEmpty() || System.currentTimeMillis()-lastDashboard>=300000) {
                CloudConfig.Connection dashboardCredentials=CloudConfig.connection(context);
                String dashboard=http("GET", "/api/v1/dashboard",null);
                stage="dashboard_decode";
                JSONObject json=new JSONObject(dashboard);
                if (json.optInt("schemaVersion",0)!=1 || !json.has("analysis")) throw new IOException("Invalid dashboard");
                CloudConfig.cacheDashboard(context,json,dashboardCredentials);
                lastDashboard=System.currentTimeMillis();
            }
            prefs.edit().putInt("failures",0).putLong("nextAttempt",0).apply();
            status(outbox.count()==0 ? "云同步正常，日报每天更新" : "正在补传历史读数");
            schedule(outbox.count()>0 ? 2000 : 300000);
            stage="idle";
        } catch (HttpFailure error) {
            diagnostic(error);
            if (CloudPolicy.permanent(error.code)) {
                prefs.edit().putBoolean("permanent",true).apply();
                status("服务器拒绝请求（HTTP "+error.code+"），已暂停，请检查服务地址和设备令牌");
            } else failed(error.code==429 ? "服务器暂时限流" : "服务器暂时不可用");
        } catch (javax.net.ssl.SSLHandshakeException error) {
            diagnostic(error);
            prefs.edit().putBoolean("permanent",true).apply(); status("HTTPS 证书校验失败，已暂停；请检查服务证书和手机时间");
        } catch (javax.net.ssl.SSLPeerUnverifiedException error) {
            diagnostic(error);
            prefs.edit().putBoolean("permanent",true).apply(); status("HTTPS 主机身份校验失败，已暂停；请检查服务证书");
        } catch (Exception error) {
            diagnostic(error);
            if(stage.endsWith("_token")) failed("设备凭据暂不可读取，待上传数据已保留");
            else if(error instanceof SocketTimeoutException) failed("云连接超时，待上传数据已保留");
            else if(error instanceof UnknownHostException) failed("服务地址暂时无法解析，待上传数据已保留");
            else if(stage.endsWith("_decode")||stage.endsWith("_ack")) failed("服务响应暂未通过校验，待上传数据已保留");
            else failed("云连接暂时失败，待上传数据已保留");
        }
    }
    private void diagnostic(Exception error) {
        // Do not pass the Throwable or message: either may contain credentials or health data.
        android.util.Log.w("OttaiCloud","stage="+stage+" exception="+error.getClass().getSimpleName());
    }
    private void failed(String message) {
        android.content.SharedPreferences prefs=CloudConfig.prefs(context);
        int failures=prefs.getInt("failures",0)+1; long delay=failures>=CloudPolicy.MAX_ATTEMPTS?1800000:CloudPolicy.delayMillis(failures);
        prefs.edit().putInt("failures",failures).putLong("nextAttempt",System.currentTimeMillis()+delay).apply();
        status(message + (failures>=CloudPolicy.MAX_ATTEMPTS ? "；暂停 30 分钟，之后新读数可重新尝试" : "；稍后重试"));
        if (failures<CloudPolicy.MAX_ATTEMPTS) schedule(delay);
    }
    private String http(String method, String path, String body) throws Exception {
        String phase="POST".equals(method)?"upload":"dashboard";
        stage=phase+"_token";
        CloudConfig.Connection credentials=CloudConfig.connection(context);
        stage=phase+"_url";
        URL url=new URL(credentials.endpoint+path);
        stage=phase+"_open_connection";
        javax.net.ssl.HttpsURLConnection connection=(javax.net.ssl.HttpsURLConnection)url.openConnection();
        try {
            stage=phase+"_configure";
            connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(10000); connection.setReadTimeout(15000);
            connection.setRequestMethod(method);
            stage=phase+"_token";
            String token=credentials.token;
            stage=phase+"_headers";
            connection.setRequestProperty("Authorization","Bearer "+token);connection.setRequestProperty("Accept","application/json");
            byte[] requestBytes=null;
            if (body!=null) {
                requestBytes=body.getBytes(StandardCharsets.UTF_8);connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type","application/json");connection.setFixedLengthStreamingMode(requestBytes.length);
            }
            stage=phase+"_connect";
            connection.connect();
            if(requestBytes!=null) {
                stage=phase+"_open_output";
                try(OutputStream stream=connection.getOutputStream()) { stage=phase+"_write_output";stream.write(requestBytes); }
            }
            stage=phase+"_response";
            int code=connection.getResponseCode();
            if (code<200 || code>=300) throw new HttpFailure(code);
            stage=phase+"_read_response";
            try(InputStream stream=connection.getInputStream(); ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[4096];int read;
                while((read=stream.read(buffer))!=-1) { if(bytes.size()+read>CloudPolicy.MAX_BODY)throw new IOException("Response too large");bytes.write(buffer,0,read); }
                return new String(bytes.toByteArray(),StandardCharsets.UTF_8);
            }
        } finally { connection.disconnect(); }
    }
    private static final class HttpFailure extends IOException { final int code; HttpFailure(int code){this.code=code;} }
}
