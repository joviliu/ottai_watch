package com.example.glucosewatch6;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.*;

final class CloudGraph extends View {
    private final List<Reading> points=new ArrayList<>();
    private final List<Reading> reference=new ArrayList<>();
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    CloudGraph(Context c) { super(c);setContentDescription("最近 24 小时血糖曲线；缺测超过 10 分钟不连接"); }
    void setData(JSONArray rows,JSONObject comparison) {
        points.clear();reference.clear();long now=System.currentTimeMillis();
        if(rows!=null)for(int i=0;i<Math.min(rows.length(),600);i++) {
            JSONObject row=rows.optJSONObject(i);if(row==null)continue;
            long at=row.optLong("sourceAt",0);double value=row.optDouble("value",Double.NaN);
            if(Reading.validValue(value)&&at>=now-86400000&&at<=now+90000)points.add(new Reading(value,at,"?"));
        }
        Collections.sort(points,(a,b)->Long.compare(a.sourceAt,b.sourceAt));invalidate();
        if(comparison!=null&&comparison.optInt("daysAvailable",0)>=3) {
            JSONArray history=comparison.optJSONArray("points");
            Calendar day=Calendar.getInstance(TimeZone.getTimeZone("Asia/Shanghai"));day.setTimeInMillis(now);
            day.set(Calendar.HOUR_OF_DAY,0);day.set(Calendar.MINUTE,0);day.set(Calendar.SECOND,0);day.set(Calendar.MILLISECOND,0);
            if(history!=null)for(int i=0;i<history.length();i++) {
                JSONObject p=history.optJSONObject(i);if(p==null||p.optInt("sampleDays",0)<3)continue;
                int minute=p.optInt("minuteOfDay",-1);double value=p.optDouble("median",Double.NaN);
                if(minute<0||minute>=1440||!Reading.validValue(value))continue;
                long at=day.getTimeInMillis()+minute*60000L;if(at>now)at-=86400000;
                reference.add(new Reading(value,at,"?"));
            }
            Collections.sort(reference,(a,b)->Long.compare(a.sourceAt,b.sourceAt));
        }
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);float scale=getResources().getDisplayMetrics().density;
        float left=30*scale,right=getWidth()-12*scale,top=15*scale,bottom=getHeight()-27*scale;
        double max=12;for(Reading p:points)max=Math.max(max,p.mmol+1);for(Reading p:reference)max=Math.max(max,p.mmol+1);
        double high=max;java.util.function.DoubleFunction<Float> y=v->(float)(bottom-v/high*(bottom-top));
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xfff2f6ff);canvas.drawRect(left,y.apply(7.8),right,y.apply(3.9),paint);
        paint.setTextSize(11*scale);paint.setStrokeWidth(scale);paint.setColor(0xffa1acba);
        for(double v:new double[]{3.9,7.8}) { canvas.drawLine(left,y.apply(v),right,y.apply(v),paint);canvas.drawText(String.format(Locale.CHINA,"%.1f",v),0,y.apply(v)+4*scale,paint); }
        if(points.isEmpty()) { paint.setColor(0xff7d8795);canvas.drawText("等待云端曲线数据",left+12*scale,(top+bottom)/2,paint);return; }
        long end=System.currentTimeMillis(),start=end-86400000;
        if(!reference.isEmpty()) {
            Path baseline=new Path();long previousReference=0;
            for(Reading p:reference) {
                float x=(float)(left+(p.sourceAt-start)/(double)86400000*(right-left)),yy=y.apply(p.mmol);
                if(previousReference==0||p.sourceAt-previousReference>2700000)baseline.moveTo(x,yy);else baseline.lineTo(x,yy);
                previousReference=p.sourceAt;
            }
            paint.setColor(0xffd7dce4);paint.setStrokeWidth(2*scale);paint.setStyle(Paint.Style.STROKE);canvas.drawPath(baseline,paint);
        }
        Path path=new Path();long previous=0;float lastX=0,lastY=0;
        for(Reading p:points) {
            float x=(float)(left+(p.sourceAt-start)/(double)86400000*(right-left)),yy=y.apply(p.mmol);
            if(previous==0||p.sourceAt-previous>600000)path.moveTo(x,yy);else path.lineTo(x,yy);
            previous=p.sourceAt;lastX=x;lastY=yy;
        }
        paint.setColor(0xff3f78ee);paint.setStrokeWidth(2.5f*scale);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);canvas.drawPath(path,paint);
        paint.setStyle(Paint.Style.FILL);paint.setColor(end-previous>=600000?0xff9aa6b5:0xff3f78ee);canvas.drawCircle(lastX,lastY,4*scale,paint);
        paint.setColor(0xff7d8795);paint.setTextSize(11*scale);java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("HH:mm",Locale.CHINA);
        canvas.drawText(f.format(new Date(start)),left,bottom+21*scale,paint);canvas.drawText(f.format(new Date(end)),right-34*scale,bottom+21*scale,paint);
    }
}
