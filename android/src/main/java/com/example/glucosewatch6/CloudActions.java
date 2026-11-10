package com.example.glucosewatch6;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import java.io.*;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import org.json.JSONObject;

/** Foreground user actions are isolated from glucose and activity delivery. */
final class CloudActions {
    interface Callback { void done(JSONObject result,int code,String error); }
    static final class Call {
        volatile javax.net.ssl.HttpsURLConnection connection;
        volatile Future<?> future;
        volatile ScheduledFuture<?> deadline;
        volatile boolean cancelled;
        void cancel() {
            cancelled=true;if(deadline!=null)deadline.cancel(false);if(future!=null)future.cancel(true);
            javax.net.ssl.HttpsURLConnection current=connection;if(current!=null)CLOCK.execute(current::disconnect);
        }
    }
    private static final ThreadPoolExecutor WORKER=new ThreadPoolExecutor(2,2,30,TimeUnit.SECONDS,new ArrayBlockingQueue<Runnable>(8));
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static final ScheduledThreadPoolExecutor CLOCK=new ScheduledThreadPoolExecutor(1);
    static { CLOCK.setRemoveOnCancelPolicy(true); }
    static Call request(Context c,String method,String path,JSONObject body,Callback callback) {
        Context app=c.getApplicationContext();Call call=new Call();
        try { call.future=WORKER.submit(()-> {
            if(call.cancelled)return;
            JSONObject result=null;int code=0;String error=null;
            try {
                CloudConfig.Connection credentials=CloudConfig.connection(app);
                if(credentials.endpoint.isEmpty()||credentials.token.isEmpty())throw new IOException();
                boolean detail=path.startsWith("/api/v1/analysis/detail");
                javax.net.ssl.HttpsURLConnection connection=(javax.net.ssl.HttpsURLConnection)new URL(credentials.endpoint+path).openConnection();call.connection=connection;
                call.deadline=CLOCK.schedule(()-> { javax.net.ssl.HttpsURLConnection current=call.connection;if(current!=null)current.disconnect(); },detail?60000:45000,TimeUnit.MILLISECONDS);
                try {
                    connection.setConnectTimeout(10000);connection.setReadTimeout(detail?45000:20000);connection.setInstanceFollowRedirects(false);
                    connection.setRequestMethod(method);connection.setRequestProperty("Authorization","Bearer "+credentials.token);
                    connection.setRequestProperty("Accept","application/json");
                    if(body!=null) {
                        byte[] data=body.toString().getBytes(StandardCharsets.UTF_8);
                        if(data.length>1_500_000)throw new IOException();
                        connection.setRequestProperty("Content-Type","application/json");connection.setDoOutput(true);connection.setFixedLengthStreamingMode(data.length);
                        try(OutputStream output=connection.getOutputStream()) { output.write(data); }
                    } else if("POST".equals(method)) {
                        // The analysis endpoint requires no body, including through the HTTPS proxy.
                        connection.setDoOutput(true);connection.setFixedLengthStreamingMode(0);
                        connection.getOutputStream().close();
                    }
                    code=connection.getResponseCode();InputStream source=code>=200&&code<300?connection.getInputStream():connection.getErrorStream();
                    if(source!=null)try(InputStream input=source;ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
                        byte[] buffer=new byte[8192];int n;
                        while((n=input.read(buffer))!=-1) { if(bytes.size()+n>2_000_000)throw new IOException();bytes.write(buffer,0,n); }
                        result=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
                    }
                    if(result==null)throw new IOException();
                    CloudConfig.Connection current=CloudConfig.connection(app);
                    if(!credentials.endpoint.equals(current.endpoint)||!credentials.token.equals(current.token)) { throw new IOException(); }
                    if(code==200&&"/api/v1/dashboard".equals(path)&&result.optInt("schemaVersion")==1) {
                        result=CloudConfig.cacheDashboard(app,result,credentials);
                    }
                    if(code<200||code>=300)error=code==409?"资料已有更新，请刷新后再试":code==429?"请求较频繁，请稍后再试":code==401||code==403?"连接权限不足，请检查设置":"请求暂未完成（HTTP "+code+"）";
                } finally { if(call.deadline!=null)call.deadline.cancel(false);connection.disconnect();call.connection=null; }
            } catch(Exception failure) { if(!call.cancelled)error="连接暂未确认，请先刷新状态"; }
            JSONObject value=result;int status=code;String message=error;
            if(!call.cancelled)MAIN.post(()-> { if(!call.cancelled)callback.done(value,status,message); });
        }); }catch(RejectedExecutionException busy) { MAIN.post(()->callback.done(null,0,"当前操作较多，请稍后再试")); }
        return call;
    }
    static Call dashboard(Context c,Callback callback) { return request(c,"GET","/api/v1/dashboard",null,callback); }
    private CloudActions() { }
}
