package com.example.glucosewatch6;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.widget.*;
import android.view.View;
import android.view.ViewGroup;
import android.app.AlertDialog;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public final class CloudActivity extends Activity {
    private EditText endpoint, token;
    private TextView status, metrics, reportTime, summary, latest, latestInfo, activitySummary;
    private LinearLayout connection;
    private LinearLayout sections;
    private CloudGraph graph;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable refresh=()->render();
    private final android.content.SharedPreferences.OnSharedPreferenceChangeListener changed=(p,k)-> {
        handler.removeCallbacks(refresh); handler.post(refresh);
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout box=MobileStyle.page(this);
        MobileStyle.text(box,"趋势与观察",26,MobileStyle.INK,true);
        MobileStyle.text(box,"过去 24 小时 · 血糖与活动",14,MobileStyle.MUTED,false);
        LinearLayout current=MobileStyle.card(box);
        LinearLayout header=new LinearLayout(this);header.setGravity(android.view.Gravity.CENTER_VERTICAL);current.addView(header);
        latest=new TextView(this);latest.setText("--");latest.setTextSize(36);latest.setTextColor(MobileStyle.BLUE);
        latest.setTypeface(android.graphics.Typeface.create("sans-serif-light",0));
        header.addView(latest,new LinearLayout.LayoutParams(0,-2,1));
        Button retry=new Button(this);retry.setText("↻");retry.setTextSize(28);retry.setTextColor(MobileStyle.BLUE);
        retry.setContentDescription("立即同步并刷新");retry.setAllCaps(false);retry.setMinWidth(0);retry.setMinimumWidth(0);
        retry.setPadding(0,0,0,0);retry.setBackground(new android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(0x203f78ee),MobileStyle.rounded(this,0x00ffffff,24),null));
        header.addView(retry,new LinearLayout.LayoutParams(MobileStyle.dp(this,48),MobileStyle.dp(this,48)));
        retry.setOnClickListener(v-> { v.animate().rotationBy(360).setDuration(450).start();CloudSync.retryNow(this);CloudSync.requestActivity(this,true,true); });
        latestInfo=MobileStyle.text(current,"mmol/L",13,MobileStyle.MUTED,false);
        status=MobileStyle.text(current,"",13,MobileStyle.MUTED,false);
        graph=new CloudGraph(this);current.addView(graph,new LinearLayout.LayoutParams(-1,MobileStyle.dp(this,225)));
        metrics=MobileStyle.text(current,"",15,MobileStyle.INK,false);
        LinearLayout health=MobileStyle.card(box);
        MobileStyle.text(health,"运动与心率",18,MobileStyle.INK,true);
        activitySummary=MobileStyle.text(health,"",14,MobileStyle.MUTED,false);
        MobileStyle.button(health,"Health Connect 连接与权限  →",()->startActivity(new Intent().setClassName(this,getPackageName()+".HealthActivity")));
        LinearLayout report=MobileStyle.card(box);
        MobileStyle.text(report,"每日观察",20,MobileStyle.VIOLET,true);
        reportTime=MobileStyle.text(report,"",12,MobileStyle.MUTED,false);summary=MobileStyle.text(report,"",17,MobileStyle.INK,true);
        sections=MobileStyle.column(this);report.addView(sections);
        MobileStyle.text(box,"趋势观察不用于确诊、药量调整或替代医生诊疗。",12,MobileStyle.MUTED,false);
        MobileStyle.button(box,"连接设置",this::showSettings);
        MobileStyle.button(box,"返回手表连接",()->finish());
        connection=MobileStyle.column(this);int pad=MobileStyle.dp(this,18);connection.setPadding(pad,pad,pad,pad);
        endpoint=new EditText(this);endpoint.setHint("HTTPS 服务地址（可含路径前缀）");endpoint.setSingleLine(true);
        endpoint.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);endpoint.setText(CloudConfig.endpoint(this));MobileStyle.field(endpoint);connection.addView(endpoint);
        token=new EditText(this);token.setHint(CloudConfig.configured(this)?"设备令牌已保存；留空保留":"设备上传令牌");token.setSingleLine(true);
        token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);MobileStyle.field(token);connection.addView(token);
        MobileStyle.button(connection,"保存连接设置",()->save(endpoint.getText().toString(),token.getText().toString()));
        MobileStyle.button(connection,"从配置文件导入",()-> {
            Intent open=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(open,41);
        });
        MobileStyle.text(connection,"仅保存本设备上传令牌；模型 API 密钥由服务器保管。离线读数会保留并等待补传。",13,MobileStyle.MUTED,false);
        CloudSync.start(this);
    }
    private TextView label(LinearLayout box,String text,int size) {
        return MobileStyle.text(box,text,size,size>=18?MobileStyle.INK:MobileStyle.MUTED,size>=18);
    }
    private void showSettings() {
        if(connection.getParent() instanceof ViewGroup)((ViewGroup)connection.getParent()).removeView(connection);
        ScrollView scroll=new ScrollView(this);scroll.addView(connection);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("连接设置").setView(scroll).setPositiveButton("完成",null).create();
        dialog.setOnDismissListener(d->token.setText(""));dialog.show();
    }
    private void save(String address,String secret) {
        try {
            String old=CloudConfig.endpoint(this);CloudConfig.save(this,address,secret);
            endpoint.setText(CloudConfig.endpoint(this));token.setText("");token.setHint("设备令牌已保存；留空保留");
            CloudSync.configured(this,!old.equals(CloudConfig.endpoint(this)));
            Toast.makeText(this,"连接设置已保存",Toast.LENGTH_SHORT).show();
        } catch (IllegalArgumentException e) { Toast.makeText(this,e.getMessage(),Toast.LENGTH_LONG).show(); }
        catch (Exception e) { Toast.makeText(this,"凭据保存失败，请重试",Toast.LENGTH_LONG).show(); }
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request!=41 || result!=RESULT_OK || data==null || data.getData()==null)return;
        try(InputStream stream=getContentResolver().openInputStream(data.getData());ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
            if(stream==null)throw new IOException();byte[] buffer=new byte[4096];int read;
            while((read=stream.read(buffer))!=-1) { if(bytes.size()+read>16384)throw new IOException();bytes.write(buffer,0,read); }
            JSONObject input=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
            String address=input.optString("endpoint",input.optString("baseURL","")), secret=input.optString("token","");
            if(!CloudPolicy.validToken(secret))throw new IOException();CloudPolicy.endpoint(address);save(address,secret);
        } catch(Exception error) { Toast.makeText(this,"配置文件无效，请核对 endpoint 和 token",Toast.LENGTH_LONG).show(); }
    }
    private static boolean contains(JSONArray values,String target) {
        if(values!=null)for(int i=0;i<values.length();i++)if(target.equals(values.optString(i)))return true;
        return false;
    }
    private String at(long value) { return value<=0?"尚无":new SimpleDateFormat("MM-dd HH:mm",Locale.CHINA).format(new Date(value)); }
    private String number(JSONObject object,String key,String unit) {
        double n=object.optDouble(key,Double.NaN);return Double.isFinite(n)?String.format(Locale.CHINA,"%.1f%s",n,unit):"--";
    }
    private void render() {
        android.content.SharedPreferences p=CloudConfig.prefs(this);
        status.setText(CloudSync.status(this)+"\n待上传 "+p.getInt("pending",0)+" 条 · 最近上传 "+at(p.getLong("lastUpload",0)));
        activitySummary.setText(HealthConnectBridge.statusText(this));
        try {
            String raw=p.getString("dashboard","");
            if(raw.isEmpty()) {
                latest.setText("--");latestInfo.setText("mmol/L · 等待读数");metrics.setText("");reportTime.setText("");sections.removeAllViews();
                graph.setData(null,null);graph.setActivity(null);
                summary.setText("等待服务器数据。完成连接后会先展示统计，积累超过 3 天后生成每日分析。");return;
            }
            JSONObject dashboard=new JSONObject(raw);graph.setData(dashboard.optJSONArray("readings"),dashboard.optJSONObject("comparison"));
            JSONObject value=dashboard.optJSONObject("latest");
            latest.setText(value==null?"--":number(value,"value","")+" "+value.optString("trend",""));
            latestInfo.setText(value==null?"mmol/L · 等待读数":"mmol/L · 更新 "+at(value.optLong("sourceAt",0)));
            JSONObject activity=dashboard.optJSONObject("activity");graph.setActivity(activity);
            if(activity!=null) {
                JSONObject stats=activity.optJSONObject("summary");if(stats==null)stats=new JSONObject();
                JSONArray kinds=activity.optJSONArray("readableKinds");
                boolean available="available".equals(activity.optString("status",""));
                String collected="运动 "+(available&&contains(kinds,"exercise")?stats.optLong("recordedExerciseCount",0)+" 段":"未同步")
                    +" · 心率 "+(available&&contains(kinds,"heart_rate")?stats.optLong("heartRateSampleCount",0)+" 个采样":"未同步")
                    +"\n步数记录 "+(available&&contains(kinds,"steps")?stats.optLong("stepRecordCount",0)+" 条":"未同步");
                activitySummary.setText(HealthConnectBridge.statusText(this)+"\n最近 24 小时："+collected
                    +(activity.optBoolean("stale",false)?"\n活动数据待更新":"")
                    +(activity.optBoolean("exerciseSessionsTruncated",false)?"\n色带仅显示前 128 段已记录运动":"\n曲线下方色带表示已记录的运动时段。"));
            }
            JSONObject m=dashboard.optJSONObject("metrics");if(m==null)m=new JSONObject();
            metrics.setText("平均 "+number(m,"mean"," mmol/L")
                +"　最高 "+number(m,"max"," mmol/L")+"\n最低 "+number(m,"min"," mmol/L")
                +"　覆盖率 "+number(m,"coveragePercent","%")+"\n观察范围内 "+number(m,"inRangePercent","%"));
            JSONObject a=dashboard.optJSONObject("analysis");if(a==null)a=new JSONObject();
            reportTime.setText("日报日期："+a.optString("reportDate","尚无")+"\n生成 "+at(a.optLong("generatedAt",0))+" · 下载 "+at(p.getLong("lastFetch",0)));
            String text=a.optString("summary","");
            if(text.isEmpty())text="ready".equals(a.optString("status"))?"日报已生成":"数据积累中；超过 3 天后生成每日分析，历史不足的比较会明确标注。";
            summary.setText(text);sections.removeAllViews();
            JSONArray rows=a.optJSONArray("sections");
            if(rows!=null)for(int i=0;i<Math.min(rows.length(),20);i++) {
                JSONObject section=rows.optJSONObject(i);if(section==null)continue;
                label(sections,section.optString("title",""),18);label(sections,section.optString("text",""),15);
            }
            JSONArray limits=a.optJSONArray("limitations");if(limits!=null&&limits.length()>0) {
                StringBuilder notes=new StringBuilder("数据与分析范围\n");for(int i=0;i<Math.min(limits.length(),20);i++)notes.append("• ").append(limits.optString(i)).append('\n');label(sections,notes.toString(),13);
            }
            JSONArray sources=a.optJSONArray("sources");if(sources!=null&&sources.length()>0) {
                StringBuilder notes=new StringBuilder("分析方法依据\n");
                for(int i=0;i<Math.min(sources.length(),10);i++) {
                    JSONObject source=sources.optJSONObject(i);if(source!=null)notes.append("• ").append(source.optString("title","")).append('\n').append(source.optString("url","")).append('\n');
                }
                TextView references=label(sections,notes.toString(),12);references.setAutoLinkMask(android.text.util.Linkify.WEB_URLS);
            }
        } catch(Exception error) { summary.setText("本地日报缓存暂不可读，请点击立即同步；手表读数不受影响。"); }
    }
    @Override public void onResume() { super.onResume();CloudConfig.prefs(this).registerOnSharedPreferenceChangeListener(changed);render(); }
    @Override public void onPause() { CloudConfig.prefs(this).unregisterOnSharedPreferenceChangeListener(changed);handler.removeCallbacks(refresh);super.onPause(); }
}
