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
    private TextView status, metrics, reportTime, summary, latest, latestInfo, activitySummary, graphNotes;
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
        graph=new CloudGraph(this);current.addView(graph,new LinearLayout.LayoutParams(-1,MobileStyle.dp(this,365)));
        graphNotes=MobileStyle.text(current,"",11,MobileStyle.MUTED,false);
        metrics=MobileStyle.text(current,"",15,MobileStyle.INK,false);
        LinearLayout health=MobileStyle.card(box);
        MobileStyle.text(health,"活动数据",18,MobileStyle.INK,true);
        activitySummary=MobileStyle.text(health,"",14,MobileStyle.MUTED,false);
        MobileStyle.button(health,"活动来源与权限  →",()->startActivity(new Intent().setClassName(this,getPackageName()+".HealthActivity")));
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
    private static JSONObject kindState(JSONObject activity,String kind) {
        JSONObject availability=activity.optJSONObject("kindAvailability");
        JSONObject state=availability==null?null:availability.optJSONObject(kind);
        if(state!=null)return state;
        JSONObject sources=activity.optJSONObject("sourceByKind"),states=activity.optJSONObject("sourceStates");
        return sources==null||states==null?null:states.optJSONObject(sources.optString(kind,""));
    }
    private static boolean kindReadable(JSONObject activity,String kind) {
        JSONObject state=kindState(activity,kind);
        return state!=null?"available".equals(state.optString("status",""))
                &&(state.has("readable")?state.optBoolean("readable",false):contains(state.optJSONArray("readableKinds"),kind))
            :"available".equals(activity.optString("status",""))&&contains(activity.optJSONArray("readableKinds"),kind);
    }
    private static boolean kindStale(JSONObject activity,String kind) {
        JSONObject state=kindState(activity,kind);
        return state!=null?state.optBoolean("stale",true):activity.optBoolean("stale",true);
    }
    private String at(long value) { return value<=0?"尚无":new SimpleDateFormat("MM-dd HH:mm",Locale.CHINA).format(new Date(value)); }
    private String number(JSONObject object,String key,String unit) {
        double n=object.optDouble(key,Double.NaN);return Double.isFinite(n)?String.format(Locale.CHINA,"%.1f%s",n,unit):"--";
    }
    private void render() {
        android.content.SharedPreferences p=CloudConfig.prefs(this);
        status.setText(CloudSync.status(this)+"\n待上传 "+p.getInt("pending",0)+" 条 · 最近上传 "+at(p.getLong("lastUpload",0)));
        String localActivity=HealthConnectBridge.statusText(this)+(PhoneStepsBridge.isEnabled(this)?"\n\n"+PhoneStepsBridge.statusText(this):"");
        activitySummary.setText(localActivity);
        try {
            String raw=p.getString("dashboard","");
            if(raw.isEmpty()) {
                latest.setText("--");latestInfo.setText("mmol/L · 等待读数");metrics.setText("");reportTime.setText("");sections.removeAllViews();
                graph.setData(null,null);graph.setActivity(null);graphNotes.setText(graph.legend());
                summary.setText("等待服务器数据。完成连接后会先展示统计，积累超过 3 天后生成每日分析。");return;
            }
            JSONObject dashboard=new JSONObject(raw);graph.setData(dashboard.optJSONArray("readings"),dashboard.optJSONObject("comparison"),dashboard.optLong("serverAt",0));
            JSONObject value=dashboard.optJSONObject("latest");
            latest.setText(value==null?"--":number(value,"value","")+" "+value.optString("trend",""));
            latestInfo.setText(value==null?"mmol/L · 等待读数":"mmol/L · 更新 "+at(value.optLong("sourceAt",0)));
            JSONObject activity=dashboard.optJSONObject("activity");graph.setActivity(activity);graphNotes.setText(graph.legend());
            if(activity!=null) {
                JSONObject stats=activity.optJSONObject("summary");if(stats==null)stats=new JSONObject();
                JSONObject sourceByKind=activity.optJSONObject("sourceByKind");
                String stepSource=sourceByKind==null?activity.optString("source",""):sourceByKind.optString("steps","");
                boolean phone="phone_steps".equals(stepSource);
                String stepsLabel=phone?"手机系统计步":"health_connect".equals(stepSource)?"小米共享步数":"步数来源待连接";
                String collected="已记录运动 "+(kindReadable(activity,"exercise")?stats.optLong("recordedExerciseCount",0)+" 段":"未同步")
                    +" · 小米共享心率 "+(kindReadable(activity,"heart_rate")?stats.optLong("heartRateSampleCount",0)+" 个采样":"未同步")
                    +"\n"+stepsLabel+"："+(kindReadable(activity,"steps")?stats.optLong("stepRecordCount",0)+" 条区间记录":"未同步");
                String total=kindReadable(activity,"steps")&&!stats.isNull("observedStepTotal")?stats.optLong("observedStepTotal",0)+" 步":"--（暂不汇总）";
                StringBuilder notes=new StringBuilder(localActivity).append("\n最近 24 小时：").append(collected)
                    .append("\n已记录步数：").append(total);
                boolean energyReadable=kindReadable(activity,"active_calories");
                String energy=energyReadable&&!stats.isNull("observedActiveKcal")?number(stats,"observedActiveKcal"," kcal"):"--（暂不汇总）";
                notes.append("\n活动热量（小米共享，估算）：")
                    .append(energyReadable?stats.optLong("activeCalorieRecordCount",0)+" 条区间 · "+energy:"未同步");
                JSONObject energyState=kindState(activity,"active_calories");
                if(energyState!=null) {
                    long first=energyState.optLong("firstRecordStartAt",0),last=energyState.optLong("lastRecordEndAt",0);
                    if(first>0&&last>0)notes.append("\n热量原始区间范围：").append(at(first)).append(" 至 ").append(at(last))
                        .append(last>System.currentTimeMillis()?"（源区间终点尚未到达）":"");
                }
                notes.append("\n热量为设备估算，来源设备未确认；不折算为步数或持续运动时长。");
                if(kindStale(activity,"heart_rate"))notes.append("\n心率资料待更新。");
                if(kindStale(activity,"steps"))notes.append("\n步数资料待更新。");
                if(kindStale(activity,"active_calories"))notes.append("\n活动热量资料待更新。");
                notes.append("\n淡紫色带：已记录的运动时段。");
                if(phone)notes.append("\n绿色计步柱仅反映手机被携带时系统提供的短批记录，不代表已确认运动。");
                if(activity.optBoolean("exerciseSessionsTruncated",false))notes.append("\n图中仅显示前 128 段运动记录。");
                if(phone&&activity.optBoolean("stepIntervalsTruncated",false))notes.append("\n原始区间明细仅保留最近 288 条；计步图汇总全部符合条件的短区间，统计保留完整记录。");
                activitySummary.setText(notes.toString());
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
