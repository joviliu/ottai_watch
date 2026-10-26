package com.example.glucosewatch6;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.*;
import com.xiaomi.xms.wearable.*;
import com.xiaomi.xms.wearable.node.*;
import com.xiaomi.xms.wearable.message.MessageApi;
import com.xiaomi.xms.wearable.auth.Permission;
import com.xiaomi.xms.wearable.service.OnServiceConnectionListener;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.json.JSONObject;

public final class BridgeService extends Service {
    private static BridgeService running;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private ApiClient client;
    private NodeApi nodes;
    private MessageApi messages;
    private String device;
    private boolean listening, registering, querying, openRequested, permissionRequested;
    private long queryStarted;
    private long lastFaceWakeAt;
    private String faceSyncKey;
    private final Runnable wakeFace = this::wakeFaceForSync;
    private final Runnable retry = new Runnable() {
        @Override public void run() {
            if (!listening) discover();
            handler.postDelayed(this, 60000);
        }
    };
    private final OnServiceConnectionListener connection = new OnServiceConnectionListener() {
        public void onServiceConnected() { handler.post(() -> { querying = false; discover(); }); }
        public void onServiceDisconnected() {
            handler.post(() -> {
                listening = registering = querying = false;
                device = null;
                client.onMessageReceivedListener = null;
                ReadingStore.status(BridgeService.this, "与小米运动健康的连接已断开，正在等待重连");
            });
        }
    };

    static void start(Context context, boolean open) {
        if (Build.VERSION.SDK_INT >= 31 && context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            ReadingStore.status(context, "请打开血糖镜像并授予附近设备权限");
            return;
        }
        try {
            context.startForegroundService(new Intent(context, BridgeService.class).putExtra("open", open));
        } catch (RuntimeException e) {
            ReadingStore.status(context, "请打开血糖镜像启动连接：" + e.getClass().getSimpleName());
        }
    }

    static void updated(Context context) {
        BridgeService service = running;
        if (service != null) service.handler.post(service::sendLatest);
    }

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("bridge", "手表血糖连接", NotificationManager.IMPORTANCE_LOW));
        PendingIntent content = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        startForeground(1, new Notification.Builder(this, "bridge").setSmallIcon(R.drawable.ic_stat_glucose)
            .setContentTitle("血糖镜像正在连接手表").setContentText("直接同步欧态的血糖值、趋势和更新时间")
            .setContentIntent(content).setOngoing(true).build());
        running = this;
        nodes = Wearable.getNodeApi(this);
        messages = Wearable.getMessageApi(this);
        client = ApiClient.getInstance(this);
        client.onServiceConnectionListener.add(connection);
        handler.post(retry);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (!faceModeEnabled()) { faceSyncKey=null; handler.removeCallbacks(wakeFace); }
        if (intent != null) permissionRequested = false;
        if (intent != null && intent.getBooleanExtra("open", false)) {
            openRequested = true; faceSyncKey = null; handler.removeCallbacks(wakeFace);
        }
        if (listening) {
            if (openRequested) openWatch(); else sendLatest();
        } else discover();
        return START_STICKY;
    }

    private void discover() {
        if (querying && System.currentTimeMillis() - queryStarted < 20000) return;
        if (client.wearableInterface == null) {
            client.openService();
            ReadingStore.status(this, "等待小米运动健康连接");
            return;
        }
        if (registering) return;
        querying = true;
        queryStarted = System.currentTimeMillis();
        nodes.getConnectedNodes(new BaseApi.Callback<List<Node>>() {
            public void onSuccess(List<Node> found) { handler.post(() -> {
                querying = false;
                if (found == null || found.isEmpty()) {
                    ReadingStore.status(BridgeService.this, "未找到已安装同签名血糖镜像的手表，请先安装 RPK");
                    return;
                }
                device = found.get(0).getId();
                authorize();
            }); }
            public void onFailure(Status status) { handler.post(() -> {
                querying = false;
                ReadingStore.status(BridgeService.this, "查找手表失败，SDK：" + status.getCode());
            }); }
        });
    }

    private void authorize() {
        registering = true;
        Permission[] needed = {Permission.DEVICE_MANAGER, Permission.NOTIFY};
        Wearable.getAuthApi(this).checkPermissions(device, needed, new BaseApi.Callback<Boolean[]>() {
            public void onSuccess(Boolean[] granted) { handler.post(() -> {
                boolean all = granted != null && granted.length == needed.length;
                if (granted != null) for (Boolean yes : granted) all &= Boolean.TRUE.equals(yes);
                if (all) { registering = false; register(); return; }
                if (permissionRequested) {
                    registering = false;
                    ReadingStore.status(BridgeService.this, "等待手表通信授权，请点击重新连接后允许");
                    return;
                }
                permissionRequested = true;
                Wearable.getAuthApi(BridgeService.this).requestPermission(device, needed, new BaseApi.Callback<Permission[]>() {
                    public void onSuccess(Permission[] result) { handler.post(() -> { registering = false; register(); }); }
                    public void onFailure(Status status) { handler.post(() -> {
                        registering = false;
                        ReadingStore.status(BridgeService.this, "请在小米运动健康允许手表通信，SDK：" + status.getCode());
                    }); }
                });
            }); }
            public void onFailure(Status status) { handler.post(() -> {
                registering = false;
                ReadingStore.status(BridgeService.this, "手表权限检查失败，SDK：" + status.getCode());
            }); }
        });
    }

    private void register() {
        if (listening || registering) return;
        registering = true;
        messages.addListener(device, (id, bytes) -> handler.post(() -> received(id, bytes)), status -> handler.post(() -> {
            registering = false;
            listening = status.isSuccess();
            ReadingStore.status(this, listening ? "手表通道已连接，等待表端回执" : "注册手表通道失败，SDK：" + status.getCode());
            if (listening) {
                nodes.subscribe(device, DataItem.ITEM_CONNECTION, (command, item, result) -> handler.post(() -> {
                    if (result.getConnectedStatus() == 1) sendLatest();
                    else ReadingStore.status(this, "手表蓝牙已断开，保留最后真实读数");
                }));
                if (openRequested) openWatch(); else sendLatest();
            }
        }));
    }

    private void received(String id, byte[] bytes) {
        if (device == null || !device.equals(id) || bytes == null || bytes.length > 16384) return;
        try {
            JSONObject message = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
            if ("request_latest".equals(message.optString("type"))) {
                android.util.Log.i("GlucoseWatch6", "Watch requested latest reading"); sendLatest();
            }
            else if ("ack".equals(message.optString("type"))) {
                String frame = ReadingStore.frame(this);
                if (!frame.isEmpty() && message.optLong("sourceAt") == new JSONObject(frame).getLong("sourceAt")) {
                    ReadingStore.ack(this, message.getLong("sourceAt"));
                }
            }
            else if ("face_export".equals(message.optString("type"))) {
                long sourceAt=message.optLong("sourceAt");
                String current=ReadingStore.frame(this);
                if (!current.isEmpty() && message.optString("frameKey").equals(faceKey(new JSONObject(current)))) {
                    getSharedPreferences(ReadingStore.PREFS,0).edit().putString("faceExportKey",message.getString("frameKey")).apply();
                    handler.removeCallbacks(wakeFace); faceSyncKey=null;
                    android.util.Log.i("GlucoseWatch6", "FACE_EXPORT sourceAt=" + sourceAt + " observedAt=" + System.currentTimeMillis());
                }
            }
        } catch (Exception e) { ReadingStore.status(this, "表端消息格式无效"); }
    }

    private void openWatch() {
        if (!listening) return;
        openRequested = false;
        nodes.launchWearApp(device, getPackageName(), status -> handler.post(() -> {
            ReadingStore.status(this, status.isSuccess() ? "已请求打开手表应用，等待真实显示回执" : "打开手表应用失败，SDK：" + status.getCode());
            if (status.isSuccess()) handler.postDelayed(this::sendLatest, 1500);
        }));
    }

    private void sendLatest() {
        if (!listening || device == null) return;
        String frame = ReadingStore.frame(this);
        if (frame.isEmpty()) { ReadingStore.status(this, "通道已连接，等待欧态真实通知"); return; }
        boolean sync = false;
        try {
            String key=faceKey(new JSONObject(frame));
            sync=key.equals(faceSyncKey);
            if (!sync) faceSyncKey=null;
        } catch (Exception e) { return; }
        if (sync) {
            try { frame = new JSONObject(frame).put("watchfaceSync",true).toString(); }
            catch (Exception e) { return; }
        }
        messages.sendMessage(device, frame.getBytes(StandardCharsets.UTF_8), status -> {
            if (!status.isSuccess()) ReadingStore.status(this, "发送失败，SDK：" + status.getCode());
            else android.util.Log.i("GlucoseWatch6", "SDK accepted frame; awaiting watch ACK");
        });
        if (!sync && faceModeEnabled()) {
            handler.removeCallbacks(wakeFace);
            handler.postDelayed(wakeFace,8000);
        }
    }

    private boolean faceModeEnabled() { return getSharedPreferences(ReadingStore.PREFS,0).getBoolean("faceMode",false); }

    private void wakeFaceForSync() {
        if (!faceModeEnabled() || !listening || device==null) return;
        try {
            JSONObject current=new JSONObject(ReadingStore.frame(this));
            long sourceAt=current.getLong("sourceAt");
            String key=faceKey(current);
            long now=System.currentTimeMillis();
            String exported=getSharedPreferences(ReadingStore.PREFS,0).getString("faceExportKey","");
            if (!FaceSyncPolicy.shouldWake(sourceAt,key,exported,now,lastFaceWakeAt)) return;
            lastFaceWakeAt=now; faceSyncKey=key;
            android.util.Log.i("GlucoseWatch6","FACE_WAKE sourceAt="+sourceAt+" observedAt="+now);
            nodes.launchWearApp(device,getPackageName(),status -> handler.post(() -> {
                if (status.isSuccess()) handler.postDelayed(this::sendLatest,1200);
                else { faceSyncKey=null; ReadingStore.status(this,"表盘同步唤起失败，SDK："+status.getCode()); }
            }));
        } catch (Exception e) { ReadingStore.status(this,"表盘同步数据无效"); }
    }
    private static String faceKey(JSONObject frame) throws org.json.JSONException {
        return FaceSyncPolicy.key(frame.getLong("sourceAt"),frame.getDouble("value"),frame.getString("trend"));
    }

    @Override public void onDestroy() {
        running = null;
        handler.removeCallbacksAndMessages(null);
        client.onServiceConnectionListener.remove(connection);
        if (listening && device != null) {
            nodes.unsubscribe(device, DataItem.ITEM_CONNECTION);
            messages.removeListener(device, status -> {});
        }
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
