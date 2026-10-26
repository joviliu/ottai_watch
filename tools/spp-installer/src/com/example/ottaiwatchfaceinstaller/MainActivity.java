package com.example.ottaiwatchfaceinstaller;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import com.example.redmiwatch6installer.xiaomi.SppConnection;
import com.example.redmiwatch6installer.xiaomi.WatchfaceParser;
import com.example.redmiwatch6installer.xiaomi.XiaomiInstaller;
import com.example.redmiwatch6installer.xiaomi.Proto;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.io.File;
import java.util.ArrayList;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final String TAG="OttaiFaceInstaller";
    private TextView status;
    private volatile boolean busy, cancelled, destroyed;
    private volatile SppConnection connection;
    private Thread operation;
    private String pendingMode;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);
        int pad=(int)(20*getResources().getDisplayMetrics().density);box.setPadding(pad,pad*2,pad,pad);
        TextView title=new TextView(this);title.setText("Ottai Watch 6 开发安装器");title.setTextSize(22);box.addView(title);
        status=new TextView(this);status.setText("从应用私有文件读取凭据与表盘。先认证，再安装本项目表盘。");status.setTextSize(16);box.addView(status);
        addButton(box,"仅认证",()->start("auth"));
        addButton(box,"认证并读取表盘数量",()->start("list"));
        addButton(box,"认证并安装 Ottai 表盘",()->start("install"));
        addButton(box,"取消并断开",this::cancel);
        ScrollView scroll=new ScrollView(this);scroll.addView(box);setContentView(scroll);
        handleIntent(getIntent());
    }
    private void addButton(LinearLayout box,String label,Runnable action) {
        Button b=new Button(this);b.setText(label);b.setOnClickListener(v->action.run());box.addView(b);
    }
    @Override protected void onNewIntent(Intent intent) {super.onNewIntent(intent);setIntent(intent);handleIntent(intent);}
    private void handleIntent(Intent intent) {
        String mode=intent.getStringExtra("mode");
        if (InstallGuard.mode(mode)) start(mode);
    }
    private void start(String mode) {
        if (busy) {line("BUSY");return;}
        if (!InstallGuard.mode(mode)) {line("Invalid operation");return;}
        if (Build.VERSION.SDK_INT>=31) {
            ArrayList<String> missing=new ArrayList<>();
            for(String p:new String[]{Manifest.permission.BLUETOOTH_CONNECT,Manifest.permission.BLUETOOTH_SCAN})
                if(checkSelfPermission(p)!=PackageManager.PERMISSION_GRANTED)missing.add(p);
            if(!missing.isEmpty()){pendingMode=mode;requestPermissions(missing.toArray(new String[0]),1);return;}
        }
        busy=true;cancelled=false;
        operation=new Thread(()->runOperation(mode),"ottai-face-install");operation.start();
    }
    private void runOperation(String mode) {
        SppConnection local=null;
        try {
            File authFile=new File(getFilesDir(),"auth.json");
            if (!authFile.isFile()||authFile.length()>4096)throw new IllegalArgumentException("Private auth.json missing or invalid");
            JSONObject auth=new JSONObject(new String(Files.readAllBytes(authFile.toPath()),StandardCharsets.UTF_8));
            String address=auth.getString("bluetoothMac").toUpperCase(Locale.ROOT), key=auth.getString("authKey");
            InstallGuard.credentials(address,key);
            WatchfaceParser face=null;
            if("install".equals(mode)||"replace".equals(mode)) {
                File bin=new File(getFilesDir(),"watchface.bin");
                if (!bin.isFile()||bin.length()<128||bin.length()>16*1024*1024)throw new IllegalArgumentException("Private watchface.bin missing or invalid");
                face=WatchfaceParser.parse(Files.readAllBytes(bin.toPath()));
                InstallGuard.face(face.valid&&face.compatibleEnoughToInstall(),face.id,face.previewWidth,face.previewHeight);
            }
            BluetoothManager manager=(BluetoothManager)getSystemService(BLUETOOTH_SERVICE);
            BluetoothAdapter adapter=manager==null?null:manager.getAdapter();
            if(adapter==null||!adapter.isEnabled())throw new IllegalStateException("Bluetooth is disabled");
            BluetoothDevice device=adapter.getRemoteDevice(address);
            final XiaomiInstaller[] receiver=new XiaomiInstaller[1];
            local=new SppConnection(adapter,device,new SppConnection.Listener(){
                public void onCommand(byte[] packet){XiaomiInstaller r=receiver[0];if(r!=null)r.onPacket(packet);}
                public void onLog(String ignored){}
                public void onDisconnected(){}
            });
            connection=local;
            receiver[0]=new XiaomiInstaller(local,new XiaomiInstaller.Progress(){
                private int last=-1;
                public void log(String message){
                    String safe = InstallGuard.safeProgress(message);
                    if (safe != null) line("STAGE " + safe);
                }
                public void progress(int percent){int p=percent/10*10;if(p!=last){last=p;line("UPLOAD "+p+"%");}}
            });
            checkCancelled();line("CONNECTING");local.connect();checkCancelled();
            line("AUTHENTICATING");receiver[0].authenticate(key);checkCancelled();line("AUTH_OK");
            if("list".equals(mode)){int count=receiver[0].faceList().size();checkCancelled();line("FACE_LIST count="+count);}
            else if(face!=null){
                if("replace".equals(mode)) {
                    String target=InstallGuard.deletionTarget(face.id);
                    boolean found=hasProjectFace(receiver[0].faceList());checkCancelled();
                    if(found) {
                        line("REPLACE_DELETE_PROJECT");receiver[0].deleteFace(target);checkCancelled();
                        // Upstream deleteFace masks a refresh failure; require an independent successful query.
                        if(hasProjectFace(receiver[0].faceList()))throw new IllegalStateException("Project face deletion not confirmed");
                        checkCancelled();line("REPLACE_DELETE_CONFIRMED");
                    }
                }
                line("INSTALLING");receiver[0].installFace(face);checkCancelled();line("INSTALL_OK");
            }
        } catch(Throwable error) {
            line(cancelled?"CANCELLED":"ERROR "+InstallGuard.safeError(error));
        } finally {
            if(local!=null)local.close();connection=null;busy=false;line("DISCONNECTED");
        }
    }
    private static boolean hasProjectFace(java.util.List<Proto.FaceInfo> faces) {
        if(faces==null)throw new IllegalStateException("Face list unavailable");
        for(Proto.FaceInfo face:faces)if(face!=null&&InstallGuard.PROJECT_FACE_ID.equals(face.id))return true;
        return false;
    }
    private void checkCancelled() throws InterruptedException {if(cancelled||destroyed||Thread.currentThread().isInterrupted())throw new InterruptedException("Cancelled");}
    private void line(String text) {
        Log.i(TAG,text);
        if(!destroyed)runOnUiThread(()->status.append("\n"+text));
    }
    private void cancel(){cancelled=true;SppConnection c=connection;if(c!=null)c.close();if(operation!=null)operation.interrupt();}
    @Override public void onRequestPermissionsResult(int request,String[] names,int[] grants) {
        super.onRequestPermissionsResult(request,names,grants);
        for(int grant:grants)if(grant!=PackageManager.PERMISSION_GRANTED){pendingMode=null;line("Bluetooth permission required");return;}
        String mode=pendingMode;pendingMode=null;if(mode!=null)start(mode);
    }
    @Override public void onDestroy(){destroyed=true;cancel();super.onDestroy();}
}
