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
    private final List<long[]> exercise=new ArrayList<>();
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
    void setActivity(JSONObject activity) {
        exercise.clear();
        JSONArray sessions=activity==null?null:activity.optJSONArray("exerciseSessions");
        if(sessions!=null)for(int i=0;i<Math.min(sessions.length(),10000);i++) {
            JSONObject row=sessions.optJSONObject(i);if(row==null)continue;
            long start=row.optLong("startAt",0),end=row.optLong("endAt",0);
            if(start>0&&end>start)exercise.add(new long[]{start,end});
        }
        setContentDescription("最近 24 小时血糖曲线；缺测超过 10 分钟不连接。下方淡紫色带表示已记录的运动时段，共 "+exercise.size()+" 段。");
        invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);float scale=getResources().getDisplayMetrics().density;
        float left=30*scale,right=getWidth()-12*scale,top=15*scale,bottom=getHeight()-42*scale;
        double max=12;for(Reading p:points)max=Math.max(max,p.mmol+1);for(Reading p:reference)max=Math.max(max,p.mmol+1);
        double high=max;java.util.function.DoubleFunction<Float> y=v->(float)(bottom-v/high*(bottom-top));
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xfff2f6ff);canvas.drawRect(left,y.apply(7.8),right,y.apply(3.9),paint);
        paint.setTextSize(11*scale);paint.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));paint.setStrokeWidth(.7f*scale);paint.setColor(0xff9aa6b8);
        for(double v:new double[]{3.9,7.8}) {
            paint.setPathEffect(new DashPathEffect(new float[]{4*scale,4*scale},0));canvas.drawLine(left,y.apply(v),right,y.apply(v),paint);paint.setPathEffect(null);
            canvas.drawText(String.format(Locale.CHINA,"%.1f",v),0,y.apply(v)+4*scale,paint);
        }
        long end=System.currentTimeMillis(),start=end-86400000;
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xffbdb0e4);
        for(long[] session:exercise) {
            if(session[1]<=start||session[0]>=end)continue;
            float x1=(float)(left+(Math.max(start,session[0])-start)/(double)86400000*(right-left));
            float x2=(float)(left+(Math.min(end,session[1])-start)/(double)86400000*(right-left));
            canvas.drawRoundRect(x1,bottom+8*scale,Math.max(x1+2*scale,x2),bottom+13*scale,2*scale,2*scale,paint);
        }
        paint.setColor(MobileStyle.MUTED);paint.setTextSize(11*scale);java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("HH:mm",Locale.CHINA);
        for(int tick=0;tick<3;tick++) {
            long at=start+tick*43200000L;float x=left+tick*(right-left)/2;String label=f.format(new Date(at));
            paint.setTextAlign(tick==0?Paint.Align.LEFT:tick==2?Paint.Align.RIGHT:Paint.Align.CENTER);
            canvas.drawText(label,x,bottom+34*scale,paint);
        }
        paint.setTextAlign(Paint.Align.LEFT);
        if(points.isEmpty()) { paint.setColor(MobileStyle.MUTED);canvas.drawText("等待云端曲线数据",left+12*scale,(top+bottom)/2,paint);return; }
        int clipped=canvas.save();canvas.clipRect(left,top,right,bottom+5*scale);
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
        canvas.restoreToCount(clipped);
    }
}
