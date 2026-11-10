package com.example.glucosewatch6;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.*;
import android.text.style.StyleSpan;
import android.view.*;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.regex.*;

public final class CloudActivity extends Activity {
    private EditText endpoint,token;
    private TextView status,metrics,reportTime,summary,latest,latestInfo,activitySummary,graphNotes,analysisState;
    private LinearLayout connection,sections;
    private Button analyze,markerList;
    private JSONArray eventRows=new JSONArray();
    private CloudGraph graph;
    private boolean rolling=true,analyzing,fetching,analysisUnconfirmed,active;
    private long analysisStarted;
    private CloudActions.Call call;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable refresh=()->render();
    private final Runnable analysisPoll=()->fetchDashboard(true);
    private final android.content.SharedPreferences.OnSharedPreferenceChangeListener changed=(p,k)-> { handler.removeCallbacks(refresh);handler.post(refresh); };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);rolling=CloudConfig.prefs(this).getBoolean("reportRolling",true);
        LinearLayout box=MobileStyle.page(this);MobileStyle.text(box,"趋势与观察",26,MobileStyle.INK,true);
        MobileStyle.text(box,"过去 24 小时 · 血糖与活动",14,MobileStyle.MUTED,false);
        LinearLayout current=MobileStyle.card(box);LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);current.addView(header);
        latest=new TextView(this);latest.setText("--");latest.setTextSize(36);latest.setTextColor(MobileStyle.BLUE);latest.setTypeface(android.graphics.Typeface.create("sans-serif-light",0));header.addView(latest,new LinearLayout.LayoutParams(0,-2,1));
        Button retry=new Button(this);retry.setText("↻");retry.setTextSize(28);retry.setTextColor(MobileStyle.BLUE);retry.setContentDescription("刷新数据");retry.setAllCaps(false);retry.setMinWidth(0);retry.setMinimumWidth(0);retry.setPadding(0,0,0,0);
        retry.setBackground(new android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf(0x203f78ee),MobileStyle.rounded(this,0x00ffffff,24),null));header.addView(retry,new LinearLayout.LayoutParams(MobileStyle.dp(this,48),MobileStyle.dp(this,48)));
        retry.setOnClickListener(v-> { v.animate().rotationBy(360).setDuration(450).start();CloudSync.retryNow(this);fetchDashboard(analyzing); });
        latestInfo=MobileStyle.text(current,"mmol/L",13,MobileStyle.MUTED,false);status=MobileStyle.text(current,"",12,MobileStyle.MUTED,false);
        graph=new CloudGraph(this);current.addView(graph,new LinearLayout.LayoutParams(-1,MobileStyle.dp(this,365)));
        graph.setTimeSelection((at,event)->openEvent(at,event));graphNotes=MobileStyle.text(current,"",11,MobileStyle.MUTED,false);metrics=MobileStyle.text(current,"",15,MobileStyle.INK,false);
        MobileStyle.button(current,"记录进餐、睡眠或运动",()->openEvent(System.currentTimeMillis(),null));
        markerList=MobileStyle.button(current,"查看时间标记",this::showMarkers);markerList.setVisibility(View.GONE);
        LinearLayout report=MobileStyle.card(box);MobileStyle.text(report,"血糖观察",20,MobileStyle.VIOLET,true);
        RadioGroup modes=new RadioGroup(this);modes.setOrientation(LinearLayout.HORIZONTAL);report.addView(modes);
        RadioButton dynamic=new RadioButton(this);dynamic.setId(101);dynamic.setText("动态 24h");dynamic.setTextColor(MobileStyle.INK);modes.addView(dynamic,new RadioGroup.LayoutParams(0,-2,1));
        RadioButton daily=new RadioButton(this);daily.setId(102);daily.setText("每日回顾");daily.setTextColor(MobileStyle.INK);modes.addView(daily,new RadioGroup.LayoutParams(0,-2,1));modes.check(rolling?101:102);
        modes.setOnCheckedChangeListener((group,id)-> { rolling=id==101;CloudConfig.prefs(this).edit().putBoolean("reportRolling",rolling).apply();render(); });
        analyze=MobileStyle.button(report,"分析过去 24 小时",this::analyzeRecent);analysisState=MobileStyle.text(report,"",12,MobileStyle.MUTED,false);
        reportTime=MobileStyle.text(report,"",12,MobileStyle.MUTED,false);summary=MobileStyle.text(report,"",17,MobileStyle.INK,true);
        summary.setMaxLines(5);summary.setEllipsize(TextUtils.TruncateAt.END);summary.setOnClickListener(v-> { summary.setMaxLines(summary.getMaxLines()==5?Integer.MAX_VALUE:5); });
        sections=MobileStyle.column(this);report.addView(sections);
        LinearLayout health=MobileStyle.card(box);MobileStyle.text(health,"活动资料",18,MobileStyle.INK,true);activitySummary=MobileStyle.text(health,"",13,MobileStyle.MUTED,false);
        MobileStyle.button(health,"活动来源与权限  →",()->startActivity(new Intent().setClassName(this,getPackageName()+".HealthActivity")));
        MobileStyle.button(box,"连接设置",this::showSettings);MobileStyle.button(box,"返回手表连接",this::finish);
        connection=MobileStyle.column(this);int pad=MobileStyle.dp(this,18);connection.setPadding(pad,pad,pad,pad);
        endpoint=new EditText(this);endpoint.setHint("HTTPS 服务地址");endpoint.setSingleLine(true);endpoint.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);endpoint.setText(CloudConfig.endpoint(this));MobileStyle.field(endpoint);connection.addView(endpoint);
        token=new EditText(this);token.setHint(CloudConfig.configured(this)?"设备令牌已保存；留空保留":"设备上传令牌");token.setSingleLine(true);token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);MobileStyle.field(token);connection.addView(token);
        MobileStyle.button(connection,"保存连接设置",()->save(endpoint.getText().toString(),token.getText().toString()));
        MobileStyle.button(connection,"从配置文件导入",()->startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE),41));
        MobileStyle.text(connection,"模型 API 密钥由服务器保管；此处只保存本设备的连接设置。",12,MobileStyle.MUTED,false);
        CloudSync.start(this);
    }
    private void openEvent(long time,JSONObject event) {
        if(event!=null) { launchEvent(time,event,event.optString("type","meal"));return; }
        String[] types={"meal","sleep","wake","exercise","note"},titles=new String[types.length];
        for(int i=0;i<types.length;i++)titles[i]=EventPolicy.title(types[i]);
        new AlertDialog.Builder(this).setTitle(at(time)).setItems(titles,(dialog,which)->launchEvent(time,null,types[which])).setNegativeButton("取消",null).show();
    }
    private void launchEvent(long time,JSONObject event,String type) {
        Intent intent=new Intent(this,EventActivity.class).putExtra("at",time).putExtra("type",type);if(event!=null)intent.putExtra("event",event.toString());startActivityForResult(intent,42);
    }
    private void showMarkers() {
        String[] labels=new String[eventRows.length()];
        for(int i=0;i<labels.length;i++) { JSONObject event=eventRows.optJSONObject(i);labels[i]=event==null?"标记":at(event.optLong("at",0))+" · "+EventPolicy.title(event.optString("type","note")); }
        new AlertDialog.Builder(this).setTitle("过去24小时的标记").setItems(labels,(dialog,which)-> { JSONObject event=eventRows.optJSONObject(which);if(event!=null)openEvent(event.optLong("at",0),event); }).setNegativeButton("返回",null).show();
    }
    private void analyzeRecent() {
        if(analyzing||analysisUnconfirmed)return;
        analyzing=true;analysisStarted=System.currentTimeMillis();render();
        call=CloudActions.request(this,"POST","/api/v1/analysis",new JSONObject(),(result,code,error)-> {
            if(isDestroyed())return;
            if(error!=null) { analysisUnconfirmed=result==null;analyzing=false;toast(result!=null&&!result.optString("reason").isEmpty()?result.optString("reason"):error); }
            fetchDashboard(true);
        });
    }
    private void fetchDashboard(boolean poll) {
        if(fetching||!active||isDestroyed())return;fetching=true;
        call=CloudActions.dashboard(this,(result,code,error)-> {
            fetching=false;if(isDestroyed())return;
            if(error==null&&result!=null) {
                analysisUnconfirmed=false;JSONObject state=result.optJSONObject("manualAnalysis");boolean running=state!=null&&"running".equals(state.optString("status"));
                analyzing=running&&System.currentTimeMillis()-analysisStarted<150000;render();
                if(poll&&analyzing&&active)handler.postDelayed(analysisPoll,5000);
            }else { if(poll)analyzing=false;render();if(!poll)toast(error==null?"刷新暂未完成":error); }
        });
    }
    private void showSettings() {
        if(connection.getParent() instanceof ViewGroup)((ViewGroup)connection.getParent()).removeView(connection);
        ScrollView scroll=new ScrollView(this);scroll.addView(connection);AlertDialog dialog=new AlertDialog.Builder(this).setTitle("连接设置").setView(scroll).setPositiveButton("完成",null).create();dialog.setOnDismissListener(d->token.setText(""));dialog.show();
    }
    private void save(String address,String secret) {
        try { String old=CloudConfig.endpoint(this);CloudConfig.save(this,address,secret);endpoint.setText(CloudConfig.endpoint(this));token.setText("");token.setHint("设备令牌已保存；留空保留");CloudSync.configured(this,!old.equals(CloudConfig.endpoint(this)));toast("连接设置已保存"); }
        catch(IllegalArgumentException e) { toast(e.getMessage()); }catch(Exception e) { toast("凭据保存失败，请重试"); }
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==42) { if(result==RESULT_OK)fetchDashboard(false);return; }
        if(request!=41||result!=RESULT_OK||data==null||data.getData()==null)return;
        try(InputStream stream=getContentResolver().openInputStream(data.getData());ByteArrayOutputStream bytes=new ByteArrayOutputStream()) {
            if(stream==null)throw new IOException();byte[] buffer=new byte[4096];int read;while((read=stream.read(buffer))!=-1) { if(bytes.size()+read>16384)throw new IOException();bytes.write(buffer,0,read); }
            JSONObject input=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));String address=input.optString("endpoint",input.optString("baseURL","")),secret=input.optString("token","");
            if(!CloudPolicy.validToken(secret))throw new IOException();CloudPolicy.endpoint(address);save(address,secret);
        }catch(Exception error) { toast("配置文件无效，请核对 endpoint 和 token"); }
    }
    private String at(long value) { return value<=0?"尚无":new SimpleDateFormat("MM-dd HH:mm",Locale.CHINA).format(new Date(value)); }
    private String number(JSONObject object,String key,String unit) { double n=object.optDouble(key,Double.NaN);return Double.isFinite(n)?String.format(Locale.CHINA,"%.1f%s",n,unit):"--"; }
    private void render() {
        android.content.SharedPreferences p=CloudConfig.prefs(this);status.setText(CloudSync.status(this));
        try {
            String raw=p.getString("dashboard","");
            if(raw.isEmpty()) {
                latest.setText("--");latestInfo.setText("mmol/L · 等待读数");metrics.setText("");reportTime.setText("");sections.removeAllViews();graph.setData(null,null);graph.setActivity(null);graph.setEvents(null);eventRows=new JSONArray();markerList.setVisibility(View.GONE);graphNotes.setText(graph.legend());summary.setText("连接后显示曲线与观察结果");analyze.setEnabled(false);analysisState.setText("等待最近24小时资料");return;
            }
            JSONObject dashboard=new JSONObject(raw);graph.setData(dashboard.optJSONArray("readings"),dashboard.optJSONObject("comparison"),dashboard.optLong("serverAt",0));graph.setActivity(dashboard.optJSONObject("activity"));graph.setEvents(dashboard.optJSONArray("events"));eventRows=dashboard.optJSONArray("events");if(eventRows==null)eventRows=new JSONArray();markerList.setVisibility(eventRows.length()>0?View.VISIBLE:View.GONE);markerList.setText("查看时间标记（"+eventRows.length()+"）");graphNotes.setText(graph.legend());
            JSONObject value=dashboard.optJSONObject("latest");latest.setText(value==null?"--":number(value,"value","")+" "+value.optString("trend",""));latestInfo.setText(value==null?"mmol/L · 等待读数":"mmol/L · 更新 "+at(value.optLong("sourceAt",0)));
            JSONObject m=dashboard.optJSONObject("metrics");if(m==null)m=new JSONObject();metrics.setText("平均 "+number(m,"mean","")+"　最高 "+number(m,"max","")+"　最低 "+number(m,"min","")+"\n观察范围内 "+number(m,"inRangePercent","%")+"　覆盖 "+number(m,"coveragePercent","%"));
            renderActivity(dashboard.optJSONObject("activity"));
            JSONObject manual=dashboard.optJSONObject("manualAnalysis");boolean running=manual!=null&&"running".equals(manual.optString("status"));
            analyze.setEnabled(manual!=null&&manual.optBoolean("eligible")&&!analyzing&&!running&&!analysisUnconfirmed);analyze.setText(analyzing||running?"分析中…":"分析过去 24 小时");
            String reason=analysisUnconfirmed?"请求暂未确认，请先刷新查看状态":manual==null?"等待分析状态":manual.optString("reason","");
            analysisState.setText(analyzing||running?"正在生成新的观察结果":reason);
            JSONObject a=dashboard.optJSONObject(rolling?"rollingAnalysis":"dailyAnalysis");
            if(a==null) { JSONObject fallback=dashboard.optJSONObject("analysis");if(fallback!=null&&((rolling&&fallback.optString("trigger").startsWith("manual"))||(!rolling&&!fallback.optString("trigger").startsWith("manual"))))a=fallback; }
            if(a==null)a=new JSONObject();
            long begin=a.optLong("periodStart",0),end=a.optLong("periodEnd",0);String time=begin>0&&end>0?at(begin)+" — "+at(end):rolling?"动态24小时":"每日回顾 · "+a.optString("reportDate","尚无");
            reportTime.setText(time+(a.optLong("generatedAt",0)>0?"\n生成于 "+at(a.optLong("generatedAt")):"")+(a.optBoolean("dataStale")?" · 资料已有更新":""));
            String text=a.optString("summary","");summary.setText(rich(text.isEmpty()?rolling?"点击上方按钮，查看过去24小时的重点变化":"尚无每日回顾":text));sections.removeAllViews();
            JSONArray highlights=a.optJSONArray("highlights");
            if(highlights!=null&&highlights.length()>0)for(int i=0;i<Math.min(highlights.length(),3);i++) { JSONObject h=highlights.optJSONObject(i);if(h!=null)highlight(h); }
            else renderLegacy(a.optJSONArray("sections"));
            renderEvidence(a);
        }catch(Exception error) { summary.setText("观察缓存暂不可读，请刷新"); }
    }
    private void renderActivity(JSONObject activity) {
        if(activity==null) { activitySummary.setText("暂无活动资料");return; }
        JSONObject stats=activity.optJSONObject("summary");if(stats==null)stats=new JSONObject();JSONObject source=activity.optJSONObject("sourceByKind");
        String steps=stats.isNull("observedStepTotal")?"--":stats.optLong("observedStepTotal")+" 步";String energy=stats.isNull("observedActiveKcal")?"--":number(stats,"observedActiveKcal"," kcal");
        activitySummary.setText("心率 "+stats.optLong("heartRateSampleCount",0)+" 个采样 · 运动 "+stats.optLong("recordedExerciseCount",0)+" 段\n"+(source!=null&&"phone_steps".equals(source.optString("steps"))?"手机步数 ":"已记录步数 ")+steps+" · 活动能量 "+energy);
    }
    private void highlight(JSONObject row) {
        String severity=row.optString("severity","info");int tint="watch".equals(severity)?0xfffff3df:"positive".equals(severity)?0xffeaf7ef:0xfff1edfc;int ink="watch".equals(severity)?0xff97642a:"positive".equals(severity)?0xff397b60:MobileStyle.VIOLET;
        LinearLayout card=MobileStyle.column(this);int pad=MobileStyle.dp(this,12);card.setPadding(pad,pad,pad,pad);card.setBackground(MobileStyle.rounded(this,tint,16));LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.topMargin=MobileStyle.dp(this,10);sections.addView(card,params);
        MobileStyle.text(card,row.optString("title",""),17,ink,true);TextView body=MobileStyle.text(card,"",15,MobileStyle.INK,false);body.setText(rich(row.optString("text","")));
        String action=row.optString("action","");if(!action.isEmpty()) { TextView next=MobileStyle.text(card,"",14,ink,true);next.setText(rich(action)); }
    }
    private void renderLegacy(JSONArray rows) {
        if(rows==null||rows.length()==0)return;LinearLayout detail=MobileStyle.column(this);detail.setVisibility(View.GONE);
        MobileStyle.button(sections,"展开报告详情",()->detail.setVisibility(detail.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));sections.addView(detail);
        for(int i=0;i<Math.min(rows.length(),12);i++) { JSONObject row=rows.optJSONObject(i);if(row==null)continue;MobileStyle.text(detail,row.optString("title",""),16,MobileStyle.VIOLET,true);MobileStyle.text(detail,row.optString("text",""),14,MobileStyle.INK,false); }
    }
    private void renderEvidence(JSONObject report) {
        JSONArray evidence=report.optJSONArray("evidence"),sources=report.optJSONArray("sources");if((evidence==null||evidence.length()==0)&&(sources==null||sources.length()==0))return;
        LinearLayout detail=MobileStyle.column(this);detail.setVisibility(View.GONE);
        MobileStyle.button(sections,"依据与延伸阅读",()->detail.setVisibility(detail.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));sections.addView(detail);
        if(evidence!=null)for(int i=0;i<Math.min(evidence.length(),3);i++) { JSONObject e=evidence.optJSONObject(i);if(e==null)continue;MobileStyle.text(detail,e.optString("title",""),14,MobileStyle.VIOLET,true);MobileStyle.text(detail,e.optString("text",""),13,MobileStyle.MUTED,false);reference(detail,e.optString("sourceUrl","")); }
        else if(sources!=null)for(int i=0;i<Math.min(sources.length(),10);i++) { JSONObject e=sources.optJSONObject(i);if(e!=null) { MobileStyle.text(detail,e.optString("title",""),13,MobileStyle.MUTED,false);reference(detail,e.optString("url","")); } }
    }
    private void reference(LinearLayout parent,String url) { if(!url.startsWith("https://"))return;TextView link=MobileStyle.text(parent,url,12,MobileStyle.BLUE,false);link.setAutoLinkMask(android.text.util.Linkify.WEB_URLS); }
    private CharSequence rich(String text) {
        String value=text==null?"":text;SpannableStringBuilder out=new SpannableStringBuilder();Matcher match=Pattern.compile("\\*\\*(.+?)\\*\\*").matcher(value);int start=0;
        while(match.find()) { out.append(value,start,match.start());int a=out.length();out.append(match.group(1));out.setSpan(new StyleSpan(android.graphics.Typeface.BOLD),a,out.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);start=match.end(); }out.append(value,start,value.length());return out;
    }
    private void toast(String message) { Toast.makeText(this,message,Toast.LENGTH_LONG).show(); }
    @Override public void onResume() { super.onResume();active=true;CloudConfig.prefs(this).registerOnSharedPreferenceChangeListener(changed);render();analysisStarted=System.currentTimeMillis();if(CloudConfig.configured(this))fetchDashboard(true); }
    @Override public void onPause() { active=false;CloudConfig.prefs(this).unregisterOnSharedPreferenceChangeListener(changed);handler.removeCallbacks(refresh);handler.removeCallbacks(analysisPoll);super.onPause(); }
    @Override public void onDestroy() { handler.removeCallbacksAndMessages(null);if(call!=null)call.cancel();super.onDestroy(); }
}
