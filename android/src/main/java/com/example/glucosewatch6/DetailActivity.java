package com.example.glucosewatch6;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.StyleSpan;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Opens a pinned report with GET; only the generation button can create a model request. */
public final class DetailActivity extends Activity {
    private String kind,reportId,connectionId="";
    private long initialStart,initialEnd,pollStarted;
    private boolean active,fetching,submitting,unconfirmed,configurationInvalid;
    private int generation;
    private JSONObject state;
    private String notice="",renderedReport="";
    private TextView period,status;
    private Button generate,query;
    private LinearLayout content;
    private CloudActions.Call call;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable poll=()->loadState();
    private final android.content.SharedPreferences.OnSharedPreferenceChangeListener changed=(p,key)-> {
        if("endpoint".equals(key)||"token".equals(key)) { checkConnection();render(); }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        kind=getIntent().getStringExtra("kind");reportId=getIntent().getStringExtra("reportId");
        if(!DetailPolicy.validIdentity(kind,reportId)) { finish();return; }
        initialStart=getIntent().getLongExtra("periodStart",0);initialEnd=getIntent().getLongExtra("periodEnd",0);
        if(saved!=null) {
            connectionId=saved.getString("connectionId","");unconfirmed=saved.getBoolean("unconfirmed");pollStarted=saved.getLong("pollStarted",0);
        }
        if(pollStarted<0||pollStarted>SystemClock.elapsedRealtime())pollStarted=0;
        try {
            String current=fingerprint();
            if(connectionId.isEmpty())connectionId=current;
            else if(!connectionId.equals(current))configurationInvalid=true;
        }catch(Exception ignored) { configurationInvalid=true; }
        LinearLayout page=MobileStyle.page(this);
        MobileStyle.text(page,"详细解读",26,MobileStyle.INK,true);
        LinearLayout header=MobileStyle.card(page);
        period=MobileStyle.text(header,"",14,MobileStyle.VIOLET,true);
        status=MobileStyle.text(header,"",13,MobileStyle.MUTED,false);
        generate=MobileStyle.button(header,"生成详细解读",this::generateDetail);
        query=MobileStyle.button(header,"查询状态",this::loadState);
        content=MobileStyle.column(this);page.addView(content);
        MobileStyle.button(page,"返回简洁报告",this::finish);
        render();
    }

    private String fingerprint() throws Exception {
        CloudConfig.Connection c=CloudConfig.connection(this);
        if(c.endpoint.isEmpty()||c.token.isEmpty())throw new IllegalStateException();
        byte[] digest=MessageDigest.getInstance("SHA-256").digest((c.endpoint+"\n"+c.token).getBytes(StandardCharsets.UTF_8));
        StringBuilder value=new StringBuilder();for(byte b:digest)value.append(String.format(Locale.ROOT,"%02x",b&255));return value.toString();
    }
    private boolean checkConnection() {
        if(!configurationInvalid)try { configurationInvalid=!connectionId.equals(fingerprint()); }catch(Exception ignored) { configurationInvalid=true; }
        if(configurationInvalid) {
            generation++;handler.removeCallbacks(poll);if(call!=null)call.cancel();fetching=false;submitting=false;state=null;
            notice="连接设置已变化，请返回后重新打开详细解读。";
        }
        return !configurationInvalid;
    }

    private void loadState() {
        if(!active||fetching||submitting||!checkConnection()) { render();return; }
        handler.removeCallbacks(poll);fetching=true;render();int sequence=++generation;
        call=CloudActions.request(this,"GET",DetailPolicy.path(kind,reportId),null,(result,code,error)-> {
            if(isDestroyed()||sequence!=generation)return;
            fetching=false;if(!checkConnection()) { render();return; }
            if(validState(result)) { state=result;unconfirmed=false;notice=error==null?"":reason(result,error);updatePollingClock(); }
            else notice=reason(result,error==null?"详细解读暂不可读，请返回刷新报告。":error);
            render();schedulePoll();
        });
    }
    private void generateDetail() {
        if(unconfirmed) { loadState();return; }
        String currentStatus=state==null?"":state.optString("status");
        if(!active||!checkConnection()||!DetailPolicy.canGenerate(currentStatus,state!=null&&state.optBoolean("eligible"),unconfirmed,fetching||submitting))return;
        try {
            JSONObject request=new JSONObject().put("kind",kind).put("reportId",reportId);
            submitting=true;pollStarted=SystemClock.elapsedRealtime();notice="";render();int sequence=++generation;
            call=CloudActions.request(this,"POST","/api/v1/analysis/detail",request,(result,code,error)-> {
                if(isDestroyed()||sequence!=generation)return;
                submitting=false;if(!checkConnection()) { render();return; }
                if(validState(result)) { state=result;unconfirmed=false;notice=error==null?"":reason(result,error);updatePollingClock(); }
                else { unconfirmed=true;notice=reason(result,error==null?"提交状态尚未确认，请查询状态。":error); }
                render();
                // Resolve a submission with GET, never replay a potentially charged POST.
                if(active)loadState();
            });
        }catch(Exception ignored) { submitting=false;notice="暂时无法发起解读，请查询状态后再试。";render(); }
    }
    private void updatePollingClock() {
        if("running".equals(state.optString("status"))) {
            if(pollStarted==0)pollStarted=SystemClock.elapsedRealtime();
        }else pollStarted=0;
    }
    private void schedulePoll() {
        handler.removeCallbacks(poll);
        if(!active||configurationInvalid)return;
        String current=state==null?"":state.optString("status");
        if((unconfirmed||"running".equals(current))&&pollStarted==0)pollStarted=SystemClock.elapsedRealtime();
        if(DetailPolicy.pollAgain(current,unconfirmed,SystemClock.elapsedRealtime()-pollStarted))handler.postDelayed(poll,5000);
    }
    private String reason(JSONObject result,String fallback) {
        String text=result==null?"":result.optString("reason","");if(text.isEmpty())text=fallback==null?"连接暂未确认，请查询状态。":fallback;
        return DetailPolicy.textLength(text)>500?text.substring(0,text.offsetByCodePoints(0,500)):text;
    }

    private void render() {
        if(period==null)return;
        long start=state==null?initialStart:time(state,"periodStart"),end=state==null?initialEnd:time(state,"periodEnd");
        if(start==0)start=initialStart;if(end==0)end=initialEnd;
        period.setText(("daily".equals(kind)?"每日回顾":"动态24h")+(start>0&&end>start?"\n"+at(start)+" — "+at(end):""));
        String current=state==null?"":state.optString("status"),message=notice;
        if(message.isEmpty()) {
            if(submitting)message="正在提交详细解读…";
            else if(unconfirmed)message="提交状态尚未确认，请先查询状态。";
            else if(state==null)message=fetching?"正在读取报告状态…":"详细解读尚未加载。";
            else if("running".equals(current)&&!DetailPolicy.pollAgain(current,false,SystemClock.elapsedRealtime()-pollStarted))message="生成时间较长，可点击查询状态；无需重新提交。";
            else message=state.optString("reason","");
        }
        JSONObject report=state==null?null:state.optJSONObject("report");
        if(report!=null&&state.optBoolean("dataStale"))message+=(message.isEmpty()?"":"\n")+"对应时段资料已有更新，下方保留上次解读。";
        long completed=state==null?0:time(state,"generatedAt");if(completed>0)message+=(message.isEmpty()?"":"\n")+"生成于 "+at(completed);
        status.setText(message);status.setVisibility(message.isEmpty()?View.GONE:View.VISIBLE);
        boolean busy=fetching||submitting;
        generate.setText(unconfirmed?"查询生成状态":submitting||"running".equals(current)?"正在生成…":report!=null&&state.optBoolean("eligible")?"生成新版解读":"生成详细解读");
        generate.setEnabled(!configurationInvalid&&(unconfirmed?!busy:DetailPolicy.canGenerate(current,state!=null&&state.optBoolean("eligible"),false,busy)));
        generate.setVisibility(report!=null&&!unconfirmed&&!submitting&&!"running".equals(current)&&!state.optBoolean("eligible")?View.GONE:View.VISIBLE);
        query.setEnabled(!configurationInvalid&&!busy);query.setText(fetching?"正在查询…":"查询状态");
        String serialized=report==null?"":report.toString();
        if(!serialized.equals(renderedReport)) { renderedReport=serialized;content.removeAllViews();if(report!=null)renderReport(report); }
    }
    private void renderReport(JSONObject report) {
        LinearLayout intro=MobileStyle.card(content);MobileStyle.text(intro,report.optString("title"),23,MobileStyle.INK,true);paragraph(intro,report.optString("summary"),17,MobileStyle.INK,true);
        JSONArray sections=report.optJSONArray("sections");
        for(int i=0;i<sections.length();i++) {
            JSONObject item=sections.optJSONObject(i);LinearLayout card=MobileStyle.card(content);
            MobileStyle.text(card,item.optString("title"),19,MobileStyle.VIOLET,true);paragraph(card,item.optString("text"),15,MobileStyle.INK,false);citations(card,item.optJSONArray("sourceIds"));
        }
        JSONArray hypotheses=report.optJSONArray("hypotheses");
        if(hypotheses.length()>0)MobileStyle.text(content,"原因假设与验证",21,MobileStyle.INK,true);
        for(int i=0;i<hypotheses.length();i++) {
            JSONObject item=hypotheses.optJSONObject(i);LinearLayout card=MobileStyle.card(content);card.setBackground(MobileStyle.rounded(this,0xfff5f1fd,24));
            MobileStyle.text(card,item.optString("title"),19,MobileStyle.VIOLET,true);
            String confidence=item.optString("confidence");MobileStyle.text(card,"strong".equals(confidence)?"依据较强":"moderate".equals(confidence)?"依据中等":"线索较弱",12,MobileStyle.MUTED,true);
            labeled(card,"支持这一解释",item.optString("support"));labeled(card,"不支持或尚缺的证据",item.optString("against"));labeled(card,"如何验证",item.optString("verification"));citations(card,item.optJSONArray("sourceIds"));
        }
        JSONArray actions=report.optJSONArray("actions");MobileStyle.text(content,"下一步可以做什么",21,MobileStyle.INK,true);
        for(int i=0;i<actions.length();i++) { JSONObject item=actions.optJSONObject(i);LinearLayout card=MobileStyle.card(content);card.setBackground(MobileStyle.rounded(this,0xffeaf7ef,24));MobileStyle.text(card,item.optString("title"),18,0xff397b60,true);paragraph(card,item.optString("text"),15,MobileStyle.INK,false); }
        JSONArray limits=report.optJSONArray("limitations");if(limits.length()>0) { LinearLayout card=MobileStyle.card(content);MobileStyle.text(card,"影响本次解读的数据缺口",17,MobileStyle.MUTED,true);for(int i=0;i<limits.length();i++)paragraph(card,limits.optString(i),14,MobileStyle.MUTED,false); }
        JSONArray sources=report.optJSONArray("sources");if(sources.length()>0) {
            LinearLayout card=MobileStyle.card(content);MobileStyle.text(card,"本次使用的研究依据",18,MobileStyle.VIOLET,true);
            for(int i=0;i<sources.length();i++) {
                JSONObject source=sources.optJSONObject(i);String url=source.optString("url");
                TextView link=MobileStyle.text(card,"["+source.optString("id")+"] "+source.optString("title"),13,MobileStyle.BLUE,false);link.setContentDescription("打开研究依据："+source.optString("title"));link.setOnClickListener(v-> { if(DetailPolicy.safeSource(url))try { startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url))); }catch(Exception ignored) { } });
            }
        }
    }
    private void labeled(LinearLayout card,String label,String text) { if(text.isEmpty())return;MobileStyle.text(card,label,14,MobileStyle.VIOLET,true);paragraph(card,text,15,MobileStyle.INK,false); }
    private void citations(LinearLayout card,JSONArray ids) {
        if(ids.length()==0)return;StringBuilder out=new StringBuilder("依据 ");for(int i=0;i<ids.length();i++) { if(i>0)out.append(" · ");out.append('[').append(ids.optString(i)).append(']'); }MobileStyle.text(card,out.toString(),12,MobileStyle.MUTED,false);
    }
    private void paragraph(LinearLayout parent,String value,int size,int color,boolean bold) {
        TextView text=MobileStyle.text(parent,"",size,color,bold);SpannableStringBuilder out=new SpannableStringBuilder();Matcher match=Pattern.compile("\\*\\*(.+?)\\*\\*").matcher(value);int start=0;
        while(match.find()) { out.append(value,start,match.start());int at=out.length();out.append(match.group(1));out.setSpan(new StyleSpan(android.graphics.Typeface.BOLD),at,out.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);start=match.end(); }out.append(value,start,value.length());text.setText(out);text.setTextIsSelectable(true);
    }
    private String at(long value) { return new SimpleDateFormat("MM-dd HH:mm",Locale.CHINA).format(new Date(value)); }
    private long time(JSONObject object,String key) { return object.isNull(key)?0:object.optLong(key,0); }

    private boolean validState(JSONObject value) {
        try {
            if(value==null||value.optInt("schemaVersion",0)!=1||!DetailPolicy.accepts(kind,reportId,value.getString("kind"),value.getString("reportId"),value.getString("status"))||!(value.get("eligible") instanceof Boolean)||!(value.get("dataStale") instanceof Boolean)||!text(value,"reason",0,500))return false;
            for(String key:new String[]{"periodStart","periodEnd","startedAt","generatedAt"}) {
                Object number=value.get(key);if(number!=JSONObject.NULL&&(!(number instanceof Number)||!Double.isFinite(((Number)number).doubleValue())||((Number)number).doubleValue()<0||((Number)number).doubleValue()!=((Number)number).longValue()||((Number)number).doubleValue()>9e15))return false;
            }
            JSONObject report=value.optJSONObject("report");if(report==null)return value.isNull("report")&&!"ready".equals(value.optString("status"));
            return validReport(report);
        }catch(Exception ignored) { return false; }
    }
    private boolean text(JSONObject object,String key,int min,int max) {
        Object value=object.opt(key);return value instanceof String&&DetailPolicy.textLength((String)value)>=min&&DetailPolicy.textLength((String)value)<=max;
    }
    private boolean validReport(JSONObject report) throws Exception {
        if(!text(report,"title",1,80)||!text(report,"summary",1,500))return false;
        JSONArray sources=report.getJSONArray("sources");if(sources.length()>32)return false;Set<String> ids=new HashSet<>();
        for(int i=0;i<sources.length();i++) { JSONObject source=sources.getJSONObject(i);if(!text(source,"id",1,64)||!source.getString("id").matches("[A-Za-z0-9_-]+")||!ids.add(source.getString("id"))||!text(source,"title",1,300)||!DetailPolicy.safeSource(source.getString("url")))return false; }
        JSONArray rows=report.getJSONArray("sections");if(rows.length()<3||rows.length()>6)return false;
        for(int i=0;i<rows.length();i++) { JSONObject item=rows.getJSONObject(i);if(!text(item,"title",1,80)||!text(item,"text",1,3500)||!validReferences(item,ids))return false; }
        rows=report.getJSONArray("hypotheses");if(rows.length()>3)return false;
        for(int i=0;i<rows.length();i++) { JSONObject item=rows.getJSONObject(i);String confidence=item.getString("confidence");if(!text(item,"title",1,80)||!text(item,"support",0,1000)||!text(item,"against",0,1000)||!text(item,"verification",0,1000)||!("strong".equals(confidence)||"moderate".equals(confidence)||"weak".equals(confidence))||!validReferences(item,ids))return false; }
        rows=report.getJSONArray("actions");if(rows.length()<1||rows.length()>5)return false;for(int i=0;i<rows.length();i++) { JSONObject item=rows.getJSONObject(i);if(!text(item,"title",1,80)||!text(item,"text",1,1200))return false; }
        rows=report.getJSONArray("limitations");if(rows.length()>3)return false;for(int i=0;i<rows.length();i++) { Object item=rows.get(i);if(!(item instanceof String)||DetailPolicy.textLength((String)item)>300)return false; }
        return true;
    }
    private boolean validReferences(JSONObject item,Set<String> ids) throws Exception {
        JSONArray refs=item.getJSONArray("sourceIds");if(refs.length()>32)return false;for(int i=0;i<refs.length();i++) { Object ref=refs.get(i);if(!(ref instanceof String)||!ids.contains(ref))return false; }return true;
    }

    @Override public void onResume() { super.onResume();active=true;CloudConfig.prefs(this).registerOnSharedPreferenceChangeListener(changed);if(checkConnection())loadState();else render(); }
    @Override public void onPause() {
        active=false;CloudConfig.prefs(this).unregisterOnSharedPreferenceChangeListener(changed);handler.removeCallbacks(poll);
        if(submitting)unconfirmed=true;
        if(fetching) { generation++;if(call!=null)call.cancel();fetching=false; }
        super.onPause();
    }
    @Override public void onSaveInstanceState(Bundle out) { out.putString("connectionId",connectionId);out.putBoolean("unconfirmed",unconfirmed||submitting||state!=null&&"running".equals(state.optString("status")));out.putLong("pollStarted",pollStarted);super.onSaveInstanceState(out); }
    @Override public void onDestroy() { generation++;handler.removeCallbacksAndMessages(null);if(call!=null)call.cancel();super.onDestroy(); }
}
