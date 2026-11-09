package com.example.glucosewatch6;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public final class CloudActivity extends Activity {
    private EditText endpoint, token;
    private TextView status, metrics, reportTime, summary;
    private LinearLayout sections;
    private CloudGraph graph;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable refresh=()->render();
    private final android.content.SharedPreferences.OnSharedPreferenceChangeListener changed=(p,k)-> {
        handler.removeCallbacks(refresh); handler.post(refresh);
    };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);
        int pad=(int)(20*getResources().getDisplayMetrics().density);box.setPadding(pad,pad,pad,pad);
        label(box,"云同步与每日观察",24);
        label(box,"最近 24 小时及长期趋势每天统一分析。3.9–7.8 是自定义观察范围；CGM 读数不能用于自行诊断糖前期或调整用药。",14);
        status=label(box,"",15);
        Button retry=new Button(this);retry.setText("立即同步 / 更新日报");retry.setOnClickListener(v->CloudSync.retryNow(this));box.addView(retry);
        graph=new CloudGraph(this);box.addView(graph,new LinearLayout.LayoutParams(-1,(int)(220*getResources().getDisplayMetrics().density)));
        metrics=label(box,"",16);reportTime=label(box,"",14);summary=label(box,"",17);
        sections=new LinearLayout(this);sections.setOrientation(LinearLayout.VERTICAL);box.addView(sections);
        label(box,"连接设置",21);
        endpoint=new EditText(this);endpoint.setHint("HTTPS 服务地址（可含路径前缀）");endpoint.setSingleLine(true);
        endpoint.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);endpoint.setText(CloudConfig.endpoint(this));box.addView(endpoint);
        token=new EditText(this);token.setHint(CloudConfig.configured(this)?"设备令牌已保存；留空保留":"设备上传令牌");token.setSingleLine(true);
        token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);box.addView(token);
        Button save=new Button(this);save.setText("保存连接设置");save.setOnClickListener(v->save(endpoint.getText().toString(),token.getText().toString()));box.addView(save);
        Button load=new Button(this);load.setText("从配置文件导入");load.setOnClickListener(v-> {
            Intent open=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(open,41);
        });box.addView(load);
        label(box,"仅保存本设备上传令牌；模型 API 密钥由服务器保管。离线读数会排队，连续失败会暂停，恢复网络或点击立即同步后继续。",13);
        Button back=new Button(this);back.setText("返回手表连接");back.setOnClickListener(v->finish());box.addView(back);
        ScrollView scroll=new ScrollView(this);scroll.addView(box);setContentView(scroll);
        CloudSync.start(this);
    }
    private TextView label(LinearLayout box,String text,int size) {
        TextView view=new TextView(this);view.setText(text);view.setTextSize(size);
        int pad=(int)(8*getResources().getDisplayMetrics().density);view.setPadding(0,pad,0,pad);box.addView(view);return view;
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
    private String at(long value) { return value<=0?"尚无":new SimpleDateFormat("MM-dd HH:mm",Locale.CHINA).format(new Date(value)); }
    private String number(JSONObject object,String key,String unit) {
        double n=object.optDouble(key,Double.NaN);return Double.isFinite(n)?String.format(Locale.CHINA,"%.1f%s",n,unit):"--";
    }
    private void render() {
        android.content.SharedPreferences p=CloudConfig.prefs(this);
        status.setText(CloudSync.status(this)+"\n待上传 "+p.getInt("pending",0)+" 条 · 最近上传 "+at(p.getLong("lastUpload",0)));
        try {
            String raw=p.getString("dashboard","");
            if(raw.isEmpty()) { summary.setText("等待服务器数据。完成连接后会先展示统计，积累超过 3 天后生成每日分析。");return; }
            JSONObject dashboard=new JSONObject(raw);graph.setData(dashboard.optJSONArray("readings"),dashboard.optJSONObject("comparison"));
            JSONObject m=dashboard.optJSONObject("metrics");if(m==null)m=new JSONObject();
            metrics.setText("最近 24 小时 · 自定义观察范围 3.9–7.8\n平均 "+number(m,"mean"," mmol/L")
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
