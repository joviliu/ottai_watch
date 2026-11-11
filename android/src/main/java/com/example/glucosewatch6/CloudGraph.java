package com.example.glucosewatch6;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import android.view.MotionEvent;
import android.view.ViewConfiguration;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.*;

/** Separate units share one time axis; missing observations are never interpolated. */
final class CloudGraph extends View {
    private static final long DAY=86400000L;
    private static final int BLUE=0xff3f78ee, HEART=0xffbf91bd, STEPS=0xff83bda6, ENERGY=0xffd7aa64, SLEEP=0xffa89acb, EXERCISE=0xff77b8a0;
    private final List<Reading> points=new ArrayList<>(),reference=new ArrayList<>();
    private final List<long[]> exercise=new ArrayList<>(),sleep=new ArrayList<>();
    private final List<HeartBin> heart=new ArrayList<>();
    private final List<AmountBin> steps=new ArrayList<>(),energy=new ArrayList<>();
    interface TimeSelection { void selected(long at,JSONObject event); }
    private TimeSelection timeSelection;
    private final List<JSONObject> events=new ArrayList<>();
    private long cursor;
    private float touchX,touchY;
    private boolean dragging,cancelled;
    void setTimeSelection(TimeSelection listener) { timeSelection=listener;setClickable(listener!=null); }
    void setEvents(JSONArray rows) {
        events.clear();if(rows!=null)for(int i=0;i<Math.min(rows.length(),500);i++) { JSONObject row=rows.optJSONObject(i);if(row!=null&&row.optLong("at",0)>=periodEnd-DAY&&row.optLong("at",0)<=periodEnd)events.add(row); }
        invalidate();
    }
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private long periodEnd=System.currentTimeMillis();
    private boolean hasActivity,stepOverlap,energyOverlap;
    private int coarseSteps,coarseEnergy,energyMinutes=15;
    private static final class HeartBin {
        long first,last;double mean,min,max;
        HeartBin(long first,long last,double mean,double min,double max) { this.first=first;this.last=last;this.mean=mean;this.min=min;this.max=max; }
    }
    private static final class AmountBin {
        long start,end;double value;
        AmountBin(long start,long end,double value) { this.start=start;this.end=end;this.value=value; }
    }
    CloudGraph(Context c) { super(c);setContentDescription("最近 24 小时血糖曲线；缺测超过 10 分钟不连接"); }
    void setData(JSONArray rows,JSONObject comparison) { setData(rows,comparison,System.currentTimeMillis()); }
    void setData(JSONArray rows,JSONObject comparison,long serverAt) {
        points.clear();reference.clear();long now=System.currentTimeMillis();
        periodEnd=serverAt>0&&serverAt<=now+90000?serverAt:now;
        if(rows!=null)for(int i=0;i<Math.min(rows.length(),600);i++) {
            JSONObject row=rows.optJSONObject(i);if(row==null)continue;
            long at=row.optLong("sourceAt",0);double value=row.optDouble("value",Double.NaN);
            if(Reading.validValue(value)&&at>=periodEnd-DAY&&at<=periodEnd)points.add(new Reading(value,at,"?"));
        }
        Collections.sort(points,(a,b)->Long.compare(a.sourceAt,b.sourceAt));
        if(comparison!=null&&comparison.optInt("daysAvailable",0)>=3) {
            JSONArray history=comparison.optJSONArray("points");
            Calendar day=Calendar.getInstance(TimeZone.getTimeZone("Asia/Shanghai"));day.setTimeInMillis(periodEnd);
            day.set(Calendar.HOUR_OF_DAY,0);day.set(Calendar.MINUTE,0);day.set(Calendar.SECOND,0);day.set(Calendar.MILLISECOND,0);
            if(history!=null)for(int i=0;i<history.length();i++) {
                JSONObject p=history.optJSONObject(i);if(p==null||p.optInt("sampleDays",0)<3)continue;
                int minute=p.optInt("minuteOfDay",-1);double value=p.optDouble("median",Double.NaN);
                if(minute<0||minute>=1440||!Reading.validValue(value))continue;
                long at=day.getTimeInMillis()+minute*60000L;if(at>periodEnd)at-=DAY;
                reference.add(new Reading(value,at,"?"));
            }
            Collections.sort(reference,(a,b)->Long.compare(a.sourceAt,b.sourceAt));
        }
        invalidate();
    }
    void setActivity(JSONObject activity) {
        hasActivity=activity!=null;exercise.clear();sleep.clear();heart.clear();steps.clear();energy.clear();
        stepOverlap=false;energyOverlap=false;coarseSteps=0;coarseEnergy=0;energyMinutes=15;
        sessions(activity==null?null:activity.optJSONArray("exerciseSessions"),exercise);
        sessions(activity==null?null:activity.optJSONArray("sleepSessions"),sleep);
        JSONArray samples=activity==null?null:activity.optJSONArray("heartRate");
        if(samples!=null)for(int i=0;i<Math.min(samples.length(),288);i++) {
            JSONObject r=samples.optJSONObject(i);if(r==null||r.optLong("sampleCount",0)<=0)continue;
            long a=r.optLong("firstSampleAt",0),b=r.optLong("lastSampleAt",0);
            double mean=r.optDouble("mean",Double.NaN),min=r.optDouble("min",Double.NaN),max=r.optDouble("max",Double.NaN);
            if(a>=periodEnd-DAY&&a<=b&&b<periodEnd&&Double.isFinite(mean)&&Double.isFinite(min)&&Double.isFinite(max)
                    &&0<min&&min<=mean&&mean<=max&&max<=300)heart.add(new HeartBin(a,b,mean,min,max));
        }
        JSONObject plot=activity==null?null:activity.optJSONObject("plot");
        if(plot!=null) {
            stepOverlap=amounts(plot.optJSONArray("steps"),"count",steps,900000);
            JSONArray halfHourly=plot.optJSONArray("activeCalories30m");
            if(halfHourly!=null)energyMinutes=30;
            energyOverlap=amounts(halfHourly!=null?halfHourly:plot.optJSONArray("activeCalories"),"energyKcal",energy,energyMinutes*60000L);
            coarseSteps=Math.max(0,plot.optInt("coarseStepRecordCount",0));
            coarseEnergy=Math.max(0,plot.optInt(halfHourly!=null?"activeCalories30mOmittedRecordCount":"coarseActiveCalorieRecordCount",0));
        }
        setContentDescription("过去 24 小时：蓝色为血糖；淡紫为 Health Connect 睡眠记录区间，淡绿为锻炼记录区间；粉紫色心率竖线为真实样本范围，点为样本均值，缺口不连接；绿色步数和琥珀色热量为各自相对记录量，按区间起点分组，不代表运动强度。粗粒度记录不画成时间柱。");
        invalidate();
    }
    private void sessions(JSONArray rows,List<long[]> output) {
        if(rows!=null)for(int i=0;i<Math.min(rows.length(),128);i++) {
            JSONObject row=rows.optJSONObject(i);if(row==null)continue;
            long[] visible=HealthPolicy.clipSession(row.optLong("startAt",0),row.optLong("endAt",0),periodEnd-DAY,periodEnd);
            if(visible!=null)output.add(visible);
        }
    }
    private boolean amounts(JSONArray rows,String key,List<AmountBin> output,long maxInterval) {
        boolean overlap=false;
        if(rows!=null)for(int i=0;i<Math.min(rows.length(),96);i++) {
            JSONObject r=rows.optJSONObject(i);if(r==null)continue;
            long a=r.optLong("startAt",0),b=r.optLong("endAt",0);double value=r.optDouble(key,Double.NaN);
            if(a>=periodEnd-DAY&&a<b&&b<=periodEnd&&b-a<=maxInterval&&Double.isFinite(value)&&value>=0) {
                output.add(new AmountBin(a,b,value));overlap|=r.optBoolean("potentialOverlap",false);
            }
        }
        return overlap;
    }
    String legend() {
        if(!hasActivity)return "缺测超过 10 分钟不连接。";
        String text="淡紫睡眠、淡绿锻炼为 HC 原始记录区间。心率为实测点与范围。步数按 15 分钟、能量按 "+energyMinutes+" 分钟分组。点按图表标记进餐等时间。";
        if(coarseSteps+coarseEnergy>0)text+=" 另有较粗时间汇总未画成分时柱。";
        return text;
    }
    private float x(long at,float left,float right) { return (float)(left+(at-(periodEnd-DAY))/(double)DAY*(right-left)); }
    private void text(Canvas c,String value,float x,float y,float size,int color,Paint.Align align) {
        paint.setStyle(Paint.Style.FILL);paint.setColor(color);paint.setAlpha(255);paint.setPathEffect(null);paint.setTextSize(size);paint.setTextAlign(align);
        paint.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));c.drawText(value,x,y,paint);
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);float d=getResources().getDisplayMetrics().density;
        float left=34*d,right=getWidth()-10*d;
        if(right<=left)return;
        float glucoseBottom=hasActivity?178*d:getHeight()-34*d;
        drawGlucose(canvas,left,right,22*d,glucoseBottom,d);
        if(hasActivity) {
            drawSessionRibbon(canvas,sleep,"睡眠",SLEEP,left,right,181*d,185*d,d);
            drawSessionRibbon(canvas,exercise,"锻炼",EXERCISE,left,right,191*d,195*d,d);
            drawHeart(canvas,left,right,216*d,257*d,d);
            text(canvas,"活动线索 · 步 15 分 / 热量 "+energyMinutes+" 分",0,278*d,10*d,MobileStyle.MUTED,Paint.Align.LEFT);
            drawAmounts(canvas,steps,"步",STEPS,left,right,289*d,306*d,d,stepOverlap);
            drawAmounts(canvas,energy,"kcal",ENERGY,left,right,319*d,336*d,d,energyOverlap);
        }
        drawMarkers(canvas,left,right,d);
        if(cursor>=periodEnd-DAY&&cursor<=periodEnd)drawCursor(canvas,left,right,d);
        float axis=hasActivity?357*d:getHeight()-9*d;
        java.text.SimpleDateFormat f=new java.text.SimpleDateFormat("HH:mm",Locale.CHINA);
        for(int tick=0;tick<3;tick++) {
            long at=periodEnd-DAY+tick*43200000L;
            text(canvas,f.format(new Date(at)),left+tick*(right-left)/2,axis,10*d,MobileStyle.MUTED,
                tick==0?Paint.Align.LEFT:tick==2?Paint.Align.RIGHT:Paint.Align.CENTER);
        }
    }
    private void drawGlucose(Canvas c,float left,float right,float top,float bottom,float d) {
        text(c,"血糖 mmol/L",0,12*d,11*d,BLUE,Paint.Align.LEFT);
        final double max=glucoseHigh();java.util.function.DoubleFunction<Float> y=v->(float)(bottom-v/max*(bottom-top));
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xfff2f6ff);c.drawRect(left,y.apply(7.8),right,y.apply(3.9),paint);
        drawSessionBackground(c,sleep,SLEEP,left,right,top,bottom);
        drawSessionBackground(c,exercise,EXERCISE,left,right,top,bottom);
        for(double v:new double[]{3.9,7.8}) {
            paint.setColor(0xffa7b2c2);paint.setStrokeWidth(.7f*d);paint.setPathEffect(new DashPathEffect(new float[]{4*d,4*d},0));
            c.drawLine(left,y.apply(v),right,y.apply(v),paint);paint.setPathEffect(null);
            text(c,String.format(Locale.CHINA,"%.1f",v),0,y.apply(v)+3*d,10*d,MobileStyle.MUTED,Paint.Align.LEFT);
        }
        if(points.isEmpty()) { text(c,"等待云端曲线数据",left+10*d,(top+bottom)/2,11*d,MobileStyle.MUTED,Paint.Align.LEFT);return; }
        int clip=c.save();c.clipRect(left,top,right,bottom+4*d);
        if(!reference.isEmpty())drawLine(c,reference,left,right,y,0xffd7dce4,1.7f*d,2700000L);
        drawLine(c,points,left,right,y,BLUE,2.5f*d,600000L);
        Reading last=points.get(points.size()-1);paint.setStyle(Paint.Style.FILL);paint.setColor(System.currentTimeMillis()-last.sourceAt>=600000?0xff9aa6b5:BLUE);
        c.drawCircle(x(last.sourceAt,left,right),y.apply(last.mmol),3.5f*d,paint);c.restoreToCount(clip);
    }
    private double glucoseHigh() {
        double high=12;for(Reading p:points)high=Math.max(high,p.mmol+1);for(Reading p:reference)high=Math.max(high,p.mmol+1);return high;
    }
    private void drawSessionBackground(Canvas c,List<long[]> rows,int color,float left,float right,float top,float bottom) {
        paint.setStyle(Paint.Style.FILL);paint.setColor(color);paint.setAlpha(18);
        for(long[] row:rows)c.drawRect(x(row[0],left,right),top,x(row[1],left,right),bottom,paint);
        paint.setAlpha(255);
    }
    private void drawSessionRibbon(Canvas c,List<long[]> rows,String label,int color,float left,float right,float top,float bottom,float d) {
        if(rows.isEmpty())return;
        text(c,label,0,bottom,8*d,color,Paint.Align.LEFT);
        paint.setStyle(Paint.Style.FILL);paint.setColor(color);paint.setAlpha(210);
        for(long[] row:rows)c.drawRoundRect(x(row[0],left,right),top,x(row[1],left,right),bottom,2*d,2*d,paint);
        paint.setAlpha(255);
    }
    private void drawLine(Canvas c,List<Reading> values,float left,float right,java.util.function.DoubleFunction<Float> y,int color,float width,long gap) {
        Path path=new Path();long previous=0;
        for(Reading p:values) { if(previous==0||p.sourceAt-previous>gap)path.moveTo(x(p.sourceAt,left,right),y.apply(p.mmol));else path.lineTo(x(p.sourceAt,left,right),y.apply(p.mmol));previous=p.sourceAt; }
        paint.setColor(color);paint.setStrokeWidth(width);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);c.drawPath(path,paint);
    }
    private void drawHeart(Canvas c,float left,float right,float top,float bottom,float d) {
        text(c,"心率 bpm · 实测采样",0,207*d,11*d,HEART,Paint.Align.LEFT);
        if(heart.isEmpty()) { text(c,"暂无可用心率采样",left+8*d,(top+bottom)/2,10*d,MobileStyle.MUTED,Paint.Align.LEFT);return; }
        double low=300,high=0;for(HeartBin p:heart) { low=Math.min(low,p.min);high=Math.max(high,p.max); }
        low=Math.max(0,Math.floor((low-5)/10)*10);high=Math.min(300,Math.ceil((high+5)/10)*10);if(high<=low)high=low+10;
        text(c,String.format(Locale.CHINA,"%.0f",high),0,top+7*d,9*d,MobileStyle.MUTED,Paint.Align.LEFT);
        text(c,String.format(Locale.CHINA,"%.0f",low),0,bottom,9*d,MobileStyle.MUTED,Paint.Align.LEFT);
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xfffcf7fb);c.drawRect(left,top,right,bottom,paint);
        int clip=c.save();c.clipRect(left-3*d,top-3*d,right+3*d,bottom+3*d);
        for(HeartBin p:heart) {
            float xx=x(p.first+(p.last-p.first)/2,left,right),a=(float)(bottom-(p.min-low)/(high-low)*(bottom-top)),b=(float)(bottom-(p.max-low)/(high-low)*(bottom-top));
            float mean=(float)(bottom-(p.mean-low)/(high-low)*(bottom-top));
            paint.setColor(HEART);paint.setAlpha(170);paint.setStrokeWidth(1.3f*d);paint.setStyle(Paint.Style.STROKE);
            if(p.min<p.max) { c.drawLine(xx,a,xx,b,paint);c.drawLine(xx-1.5f*d,a,xx+1.5f*d,a,paint);c.drawLine(xx-1.5f*d,b,xx+1.5f*d,b,paint); }
            paint.setStyle(Paint.Style.FILL);paint.setAlpha(255);c.drawCircle(xx,mean,2*d,paint);
        }
        c.restoreToCount(clip);
    }
    private void drawAmounts(Canvas c,List<AmountBin> rows,String unit,int color,float left,float right,float top,float bottom,float d,boolean overlap) {
        double max=0;for(AmountBin p:rows)max=Math.max(max,p.value);
        text(c,unit,0,bottom-2*d,10*d,color,Paint.Align.LEFT);
        text(c,rows.isEmpty()?"暂无可绘制的短区间记录":(overlap?"含重叠 · ":"")+"单组最高 "+compact(max)+" "+unit,right,top-4*d,9*d,MobileStyle.MUTED,Paint.Align.RIGHT);
        paint.setStyle(Paint.Style.FILL);paint.setColor(0xfff4f6f9);c.drawRect(left,top,right,bottom,paint);
        if(max<=0) { text(c,rows.isEmpty()?"缺测不代表没有活动":"原始区间记录量为 0",left+7*d,bottom-4*d,9*d,MobileStyle.MUTED,Paint.Align.LEFT);return; }
        int clip=c.save();c.clipRect(left,top,right,bottom);
        for(AmountBin p:rows) {
            if(p.value<=0)continue;float a=x(p.start,left,right),b=x(p.end,left,right);
            float inset=Math.min(.4f*d,(b-a)/5);paint.setColor(color);paint.setAlpha(overlap?150:220);
            c.drawRect(a+inset,(float)(bottom-p.value/max*(bottom-top)),b-inset,bottom,paint);
        }
        paint.setAlpha(255);c.restoreToCount(clip);
    }
    private void drawMarkers(Canvas c,float left,float right,float d) {
        int saved=c.save();c.clipRect(left-7*d,16*d,right+7*d,40*d);
        for(JSONObject event:events) {
            float xx=x(event.optLong("at"),left,right);paint.setStyle(Paint.Style.FILL);paint.setColor(0xfff2ecff);paint.setAlpha(255);c.drawCircle(xx,27*d,7*d,paint);
            text(c,EventPolicy.marker(event.optString("type")),xx,30*d,8*d,MobileStyle.VIOLET,Paint.Align.CENTER);
        }
        c.restoreToCount(saved);
    }
    private void drawCursor(Canvas c,float left,float right,float d) {
        Reading sample=EventPolicy.nearestReading(points,cursor);
        java.text.SimpleDateFormat clock=new java.text.SimpleDateFormat("HH:mm",Locale.CHINA);
        String title=sample==null?"无读数":clock.format(new Date(sample.sourceAt))+" · "+String.format(Locale.CHINA,"%.1f mmol/L",sample.mmol);
        float pillTop=36*d,pillBottom=54*d;
        float xx=x(cursor,left,right);paint.setColor(0xff8292ad);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(.8f*d);paint.setPathEffect(new DashPathEffect(new float[]{3*d,3*d},0));
        c.drawLine(xx,pillBottom,xx,hasActivity?178*d:getHeight()-30*d,paint);
        if(hasActivity) { c.drawLine(xx,216*d,xx,257*d,paint);c.drawLine(xx,289*d,xx,306*d,paint);c.drawLine(xx,319*d,xx,336*d,paint); }paint.setPathEffect(null);
        if(sample!=null) {
            float bottom=hasActivity?178*d:getHeight()-34*d,yy=(float)(bottom-sample.mmol/glucoseHigh()*(bottom-22*d));
            int selected=c.save();c.clipRect(left,22*d,right,bottom+4*d);
            paint.setStyle(Paint.Style.FILL);paint.setColor(0xffffffff);c.drawCircle(x(sample.sourceAt,left,right),yy,4*d,paint);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1.5f*d);paint.setColor(BLUE);c.drawCircle(x(sample.sourceAt,left,right),yy,4*d,paint);c.restoreToCount(selected);
        }
        paint.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));paint.setTextSize(10*d);
        float pillWidth=Math.min(right-left,Math.max(64*d,paint.measureText(title)+20*d));
        float a=Math.max(left,Math.min(right-pillWidth,xx-pillWidth/2));paint.setStyle(Paint.Style.FILL);paint.setColor(0xffe9effa);
        int bubble=c.save();c.clipRect(left,pillTop,right,pillBottom);c.drawRoundRect(a,pillTop,a+pillWidth,pillBottom,8*d,8*d,paint);
        text(c,title,a+pillWidth/2,49*d,10*d,MobileStyle.INK,Paint.Align.CENTER);
        c.restoreToCount(bubble);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if(timeSelection==null)return super.onTouchEvent(event);
        float d=getResources().getDisplayMetrics().density,left=34*d,right=getWidth()-10*d;
        switch(event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                if(event.getX()<left||event.getX()>right)return false;
                touchX=event.getX();touchY=event.getY();dragging=false;cancelled=false;cursor=EventPolicy.timeAt(touchX,left,right,periodEnd);invalidate();return true;
            case MotionEvent.ACTION_MOVE:
                float dx=event.getX()-touchX,dy=event.getY()-touchY;int slop=ViewConfiguration.get(getContext()).getScaledTouchSlop();
                if(!dragging&&EventPolicy.vertical(dx,dy,slop)) { cancelled=true;cursor=0;invalidate();return false; }
                if(EventPolicy.horizontal(dx,dy,slop)) { dragging=true;getParent().requestDisallowInterceptTouchEvent(true); }
                if(dragging) { cursor=EventPolicy.timeAt(event.getX(),left,right,periodEnd);invalidate(); }return true;
            case MotionEvent.ACTION_UP:
                getParent().requestDisallowInterceptTouchEvent(false);
                if(cancelled)return false;
                JSONObject nearest=null;float distance=10*d;
                if(!dragging&&event.getY()<42*d)for(JSONObject row:events) { float diff=Math.abs(x(row.optLong("at"),left,right)-event.getX());if(diff<distance) { distance=diff;nearest=row; } }
                if(nearest!=null) { cursor=nearest.optLong("at");timeSelection.selected(cursor,nearest);invalidate(); }
                else performClick();return true;
            case MotionEvent.ACTION_CANCEL:
                cancelled=true;cursor=0;getParent().requestDisallowInterceptTouchEvent(false);invalidate();return false;
        }
        return true;
    }
    @Override public boolean performClick() {
        super.performClick();if(timeSelection!=null)timeSelection.selected(cursor>0?cursor:Math.min(periodEnd,System.currentTimeMillis()),null);return true;
    }
    private String compact(double value) {
        if(value>=10000)return String.format(Locale.CHINA,"%.1f万",value/10000);
        return String.format(Locale.CHINA,value==Math.rint(value)?"%.0f":"%.1f",value);
    }
}
