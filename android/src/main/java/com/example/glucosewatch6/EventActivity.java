package com.example.glucosewatch6;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
import android.text.*;
import android.view.View;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

/** A user-confirmed time marker. Photos are only uploaded by the recognition button. */
public final class EventActivity extends Activity {
    private static final String[] TYPES={"meal","sleep","wake","exercise","note"};
    private static final ThreadPoolExecutor PHOTOS=new ThreadPoolExecutor(1,1,30,TimeUnit.SECONDS,new ArrayBlockingQueue<Runnable>(2));
    private final Handler handler=new Handler(Looper.getMainLooper());
    private long at,expectedUpdatedAt,pollStarted;
    private String id,type="meal",mealSource="manual",photoName="",cameraName="",requestId="";
    private boolean editing,saving,photoBusy,recognitionPending,recognitionAttempted,active;
    private JSONObject usage;
    private TextView timeLabel,photoStatus,usageText;
    private EditText note,foods,kcalLow,kcalHigh;
    private LinearLayout mealCard;
    private ImageView photo;
    private Button save,recognize,capture,choose;
    private Spinner kinds;
    private Bitmap thumbnail;
    private CloudActions.Call action;
    private Future<?> photoWork;
    private int photoGeneration;
    private final Runnable poll=()->pollRecognition();

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);cleanupOldPhotos();
        id=UUID.randomUUID().toString();type=getIntent().getStringExtra("type");if(type==null)type="meal";at=getIntent().getLongExtra("at",System.currentTimeMillis());
        JSONObject original=null;
        try { String raw=state!=null?state.getString("draft",""):getIntent().getStringExtra("event");if(raw!=null&&!raw.isEmpty())original=new JSONObject(raw); }catch(Exception ignored) { }
        if(original!=null) { id=original.optString("id",id);type=original.optString("type","meal");at=original.optLong("at",at);expectedUpdatedAt=original.optLong("updatedAt",0);editing=expectedUpdatedAt>0; }
        if(state!=null) {
            photoName=safeName(state.getString("photoName",""));cameraName=safeName(state.getString("cameraName",""));requestId=state.getString("requestId","");
            recognitionPending=state.getBoolean("recognitionPending");recognitionAttempted=state.getBoolean("recognitionAttempted");
        }
        LinearLayout box=MobileStyle.page(this);MobileStyle.text(box,editing?"编辑时间标记":"记录这一刻",26,MobileStyle.INK,true);
        MobileStyle.text(box,"将进餐、睡眠与血糖变化放在同一条时间线上",13,MobileStyle.MUTED,false);
        LinearLayout details=MobileStyle.card(box);
        timeLabel=MobileStyle.text(details,"",22,MobileStyle.BLUE,true);timeLabel.setOnClickListener(v->pickTime());
        MobileStyle.button(details,"调整日期与时间",this::pickTime);
        kinds=new Spinner(this);String[] titles=new String[TYPES.length];int selected=0;
        for(int i=0;i<TYPES.length;i++) { titles[i]=EventPolicy.title(TYPES[i]);if(TYPES[i].equals(type))selected=i; }
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,titles);kinds.setAdapter(adapter);
        kinds.setBackground(MobileStyle.rounded(this,0xffeef4ff,12));details.addView(kinds,new LinearLayout.LayoutParams(-1,MobileStyle.dp(this,52)));kinds.setSelection(selected);
        note=field(details,"备注（可选）",false);note.setFilters(new InputFilter[]{new InputFilter.LengthFilter(EventPolicy.MAX_NOTE)});
        if(original!=null)note.setText(original.optString("note",""));
        mealCard=MobileStyle.card(box);MobileStyle.text(mealCard,"这餐吃了什么",20,MobileStyle.VIOLET,true);
        foods=field(mealCard,"例如：一碗米饭、清蒸鱼、炒青菜",false);foods.setMinLines(3);foods.setFilters(new InputFilter[]{new InputFilter.LengthFilter(EventPolicy.MAX_FOODS)});
        MobileStyle.text(mealCard,"估计热量（可留空）",13,MobileStyle.MUTED,false);
        LinearLayout range=new LinearLayout(this);mealCard.addView(range);
        kcalLow=new EditText(this);kcalHigh=new EditText(this);
        for(EditText input:new EditText[]{kcalLow,kcalHigh}) { input.setInputType(android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);MobileStyle.field(input);range.addView(input,new LinearLayout.LayoutParams(0,-2,1)); }
        kcalLow.setHint("最低 kcal");kcalHigh.setHint("最高 kcal");
        if(original!=null) {
            JSONObject meal=original.optJSONObject("meal");if(meal!=null) { foods.setText(meal.optString("foods",""));mealSource=meal.optString("source","manual");if(!meal.isNull("estimatedKcalMin"))kcalLow.setText(decimal(meal.optDouble("estimatedKcalMin")));if(!meal.isNull("estimatedKcalMax"))kcalHigh.setText(decimal(meal.optDouble("estimatedKcalMax"))); }
        }
        photo=new ImageView(this);photo.setScaleType(ImageView.ScaleType.CENTER_CROP);photo.setVisibility(View.GONE);mealCard.addView(photo,new LinearLayout.LayoutParams(-1,MobileStyle.dp(this,160)));
        capture=MobileStyle.button(mealCard,"拍照添加餐食",this::takePhoto);choose=MobileStyle.button(mealCard,"选择已有照片",this::choosePhoto);
        recognize=MobileStyle.button(mealCard,"识别餐食",this::recognizePhoto);
        photoStatus=MobileStyle.text(mealCard,"选择照片后，点击识别才会上传。识别结果可直接修改。",12,MobileStyle.MUTED,false);
        usageText=MobileStyle.text(mealCard,"识别完成后显示本次用量",11,MobileStyle.MUTED,false);usageText.setVisibility(View.GONE);
        MobileStyle.button(mealCard,"本次识别用量",()->usageText.setVisibility(usageText.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));
        save=MobileStyle.button(box,"保存标记",this::saveEvent);
        if(editing)MobileStyle.button(box,"删除这条标记",()->new AlertDialog.Builder(this).setTitle("删除标记？").setMessage("这条标记将从时间线上移除。").setNegativeButton("取消",null).setPositiveButton("删除",(d,w)->deleteEvent()).show());
        MobileStyle.button(box,"返回",this::finish);
        kinds.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() { public void onItemSelected(android.widget.AdapterView<?> p,View v,int position,long row) { type=TYPES[position];mealCard.setVisibility("meal".equals(type)?View.VISIBLE:View.GONE); }public void onNothingSelected(android.widget.AdapterView<?> p) { } });
        mealCard.setVisibility("meal".equals(type)?View.VISIBLE:View.GONE);updateTime();showPhoto();updateButtons();
    }
    private EditText field(LinearLayout box,String hint,boolean single) { EditText input=new EditText(this);input.setHint(hint);input.setSingleLine(single);MobileStyle.field(input);box.addView(input);return input; }
    private String safeName(String value) { return value!=null&&value.matches("[a-f0-9-]{36}\\.jpg")?value:""; }
    private File preparedPhoto() { return new File(getCacheDir(),"meal-photo-"+photoName); }
    private String decimal(double value) { return Double.isFinite(value)?String.format(Locale.CHINA,value==Math.rint(value)?"%.0f":"%.1f",value):""; }
    private String clean(String value) { return value.replaceAll("\\p{Cntrl}"," ").replaceAll("\\s+"," ").trim(); }
    private void updateTime() { timeLabel.setText(new SimpleDateFormat("MM月dd日 HH:mm",Locale.CHINA).format(new Date(at))); }
    private void pickTime() {
        Calendar c=Calendar.getInstance();c.setTimeInMillis(at);
        new DatePickerDialog(this,(picker,y,m,d)-> { c.set(y,m,d);new TimePickerDialog(this,(clock,h,min)-> { c.set(Calendar.HOUR_OF_DAY,h);c.set(Calendar.MINUTE,min);c.set(Calendar.SECOND,0);c.set(Calendar.MILLISECOND,0);at=c.getTimeInMillis();updateTime(); },c.get(Calendar.HOUR_OF_DAY),c.get(Calendar.MINUTE),true).show(); },c.get(Calendar.YEAR),c.get(Calendar.MONTH),c.get(Calendar.DAY_OF_MONTH)).show();
    }
    private JSONObject draft(boolean validate) throws Exception {
        if(validate&&!EventPolicy.validTime(at,System.currentTimeMillis()))throw new IllegalArgumentException("请选择最近一年内、尚未超过当前五分钟的时间");
        JSONObject event=new JSONObject().put("id",id).put("type",type).put("at",at).put("note",clean(note.getText().toString()));
        if(expectedUpdatedAt>0)event.put("expectedUpdatedAt",expectedUpdatedAt);
        if("meal".equals(type)) {
            String low=kcalLow.getText().toString().trim(),high=kcalHigh.getText().toString().trim();
            if(validate&&!EventPolicy.validRange(low,high))throw new IllegalArgumentException("请填写完整、由低到高的热量范围，或同时留空");
            JSONObject meal=new JSONObject().put("foods",clean(foods.getText().toString())).put("source",mealSource);
            if(low.isEmpty()||high.isEmpty()||!EventPolicy.validRange(low,high))meal.put("estimatedKcalMin",JSONObject.NULL).put("estimatedKcalMax",JSONObject.NULL);
            else meal.put("estimatedKcalMin",Double.parseDouble(low)).put("estimatedKcalMax",Double.parseDouble(high));
            event.put("meal",meal);
        }
        return event;
    }
    private void saveEvent() {
        if(saving)return;
        try {
            JSONObject event=draft(true);saving=true;updateButtons();
            action=CloudActions.request(this,"POST","/api/v1/events",event,(result,code,error)-> {
                if(isDestroyed())return;saving=false;updateButtons();
                if(error!=null||result==null||!result.optBoolean("ok")) { toast(error==null?"标记暂未保存，请重试":error);return; }
                setResult(RESULT_OK);toast("标记已保存");finish();
            });
        }catch(Exception error) { toast(error instanceof IllegalArgumentException?error.getMessage():"请检查标记内容"); }
    }
    private void deleteEvent() {
        if(saving)return;
        try {
            saving=true;updateButtons();JSONObject body=new JSONObject().put("id",id);if(expectedUpdatedAt>0)body.put("expectedUpdatedAt",expectedUpdatedAt);
            action=CloudActions.request(this,"POST","/api/v1/events/delete",body,(result,code,error)-> {
                if(isDestroyed())return;saving=false;updateButtons();if(error!=null||result==null||!result.optBoolean("ok")) { toast(error==null?"删除暂未完成":error);return; }
                setResult(RESULT_OK);finish();
            });
        }catch(Exception error) { saving=false;updateButtons();toast("删除暂未完成"); }
    }
    private void takePhoto() {
        if(photoBusy||recognitionPending)return;
        cameraName=UUID.randomUUID()+".jpg";Uri uri=MealPhotoProvider.uri(this,cameraName);
        Intent intent=new Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT,uri).addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.setClipData(ClipData.newRawUri("meal-photo",uri));
        try { startActivityForResult(intent,51); }catch(ActivityNotFoundException error) { cameraName="";toast("没有可用的相机应用，请选择已有照片"); }
    }
    private void choosePhoto() {
        if(photoBusy||recognitionPending)return;
        try { startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE),52); }
        catch(ActivityNotFoundException error) { toast("无法打开图片选择器"); }
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request==51) {
            String name=cameraName;cameraName="";if(name.isEmpty())return;Uri uri=MealPhotoProvider.uri(this,name);
            File captured=new File(MealPhotoProvider.directory(this),name);
            if(result==RESULT_OK&&captured.isFile()&&captured.length()>0)importPhoto(uri,captured);
            else { captured.delete();revokeUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION); }
        } else if(request==52&&result==RESULT_OK&&data!=null&&data.getData()!=null)importPhoto(data.getData(),null);
    }
    private void importPhoto(Uri uri,File captured) {
        photoBusy=true;updateButtons();photoStatus.setText("正在准备照片…");int generation=++photoGeneration;
        Context app=getApplicationContext();
        try { photoWork=PHOTOS.submit(()-> {
            File output=null;String failure=null;
            try { byte[] bytes=MealPhoto.prepare(app,uri);output=new File(app.getCacheDir(),"meal-photo-"+UUID.randomUUID()+".jpg");try(OutputStream stream=new FileOutputStream(output)) { stream.write(bytes); } }
            catch(Exception|OutOfMemoryError error) { if(output!=null)output.delete();output=null;failure="照片暂不可读取，请换一张较小的图片"; }
            finally { if(captured!=null) { captured.delete();try { app.revokeUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION); }catch(SecurityException ignored) { } } }
            File prepared=output;String message=failure;
            handler.post(()-> {
                if(isDestroyed()||generation!=photoGeneration) { if(prepared!=null)prepared.delete();return; }
                photoBusy=false;
                if(message!=null||prepared==null)photoStatus.setText(message==null?"照片准备失败":message);
                else {
                    if(!photoName.isEmpty())preparedPhoto().delete();photoName=prepared.getName().substring("meal-photo-".length());requestId=UUID.randomUUID().toString();recognitionAttempted=false;recognitionPending=false;usage=null;
                    showPhoto();photoStatus.setText("照片已准备，点击识别后上传");
                }
                updateButtons();
            });
        }); }catch(RejectedExecutionException busy) { if(captured!=null) { captured.delete();revokeUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION); }photoBusy=false;updateButtons();photoStatus.setText("照片处理较忙，请稍后再试"); }
    }
    private void showPhoto() {
        if(thumbnail!=null) { photo.setImageDrawable(null);thumbnail.recycle();thumbnail=null; }
        if(!photoName.isEmpty()&&preparedPhoto().isFile()) {
            BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=2;thumbnail=BitmapFactory.decodeFile(preparedPhoto().getPath(),options);
            if(thumbnail!=null) { photo.setImageBitmap(thumbnail);photo.setVisibility(View.VISIBLE);return; }
        }
        photoName="";photo.setVisibility(View.GONE);
    }
    private void recognizePhoto() {
        if(photoBusy||recognitionPending||photoName.isEmpty())return;
        if(recognitionAttempted) { recognitionPending=true;pollStarted=System.currentTimeMillis();updateButtons();pollRecognition();return; }
        try {
            File file=preparedPhoto();if(!file.isFile()||file.length()>EventPolicy.MAX_IMAGE)throw new IOException();
            byte[] bytes;try(InputStream in=new FileInputStream(file);ByteArrayOutputStream out=new ByteArrayOutputStream()) { byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)out.write(b,0,n);bytes=out.toByteArray(); }
            if(requestId.isEmpty())requestId=UUID.randomUUID().toString();
            JSONObject body=new JSONObject().put("requestId",requestId).put("mimeType","image/jpeg").put("imageBase64",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP));
            recognitionAttempted=true;recognitionPending=true;pollStarted=System.currentTimeMillis();photoStatus.setText("正在识别餐食…");updateButtons();
            action=CloudActions.request(this,"POST","/api/v1/meals/recognize",body,(result,code,error)->recognitionResult(result,code,error));
        }catch(Exception error) { photoStatus.setText("照片暂不可读取，请重新选择"); }
    }
    private void pollRecognition() {
        if(!active||!recognitionPending||isDestroyed())return;
        if(System.currentTimeMillis()-pollStarted>120000) { recognitionPending=false;updateButtons();photoStatus.setText("识别仍未确认，可查询结果；不会自动重复提交");return; }
        action=CloudActions.request(this,"GET","/api/v1/meals/recognize?requestId="+Uri.encode(requestId),null,(result,code,error)->recognitionResult(result,code,error));
    }
    private void recognitionResult(JSONObject result,int code,String error) {
        if(isDestroyed())return;
        if(code==404) { recognitionPending=false;recognitionAttempted=false;photoStatus.setText("尚未找到这次识别，可提交同一请求重试");updateButtons();return; }
        if(error!=null||result==null) { recognitionPending=false;photoStatus.setText(error==null?"识别状态暂未确认，可查询结果":error+"；可查询原请求结果");updateButtons();return; }
        String state=result.optString("status",result.has("recognition")?"ready":"running");
        if("running".equals(state)) { recognitionPending=true;photoStatus.setText("正在识别餐食…");if(active)handler.postDelayed(poll,3000);updateButtons();return; }
        recognitionPending=false;usage=result.optJSONObject("usage");
        if("ready".equals(state)) {
            JSONObject meal=result.optJSONObject("recognition");
            if(meal!=null&&meal.optBoolean("isFoodImage",false)) {
                foods.setText(meal.optString("foods",""));kcalLow.setText(meal.isNull("estimatedKcalMin")?"":decimal(meal.optDouble("estimatedKcalMin")));kcalHigh.setText(meal.isNull("estimatedKcalMax")?"":decimal(meal.optDouble("estimatedKcalMax")));mealSource="photo_estimate";
                photoStatus.setText("识别完成，可修改餐食、份量与热量后保存");
            }else photoStatus.setText("没有识别到餐食，可手动填写或更换照片");
        } else photoStatus.setText("本次识别未完成，可手动填写或更换照片");
        usageText.setText(usageDescription());updateButtons();
    }
    private String usageDescription() {
        if(usage==null)return "尚无已确认用量";
        if(usage.optBoolean("cacheHit",false))return "复用已识别结果 · 本次未新增识别用量";
        if(!usage.optBoolean("usageAvailable",true)||usage.isNull("inputTokens")||usage.isNull("outputTokens"))return "用量暂未返回";
        return "输入 "+usage.optLong("inputTokens",0)+" / 输出 "+usage.optLong("outputTokens",0)+" token"+costText(usage);
    }
    private String costText(JSONObject data) {
        double usd=data.optDouble("estimatedCostUsd",Double.NaN);return Double.isFinite(usd)?String.format(Locale.CHINA," · 估计 $%.5f",usd):"";
    }
    private void updateButtons() {
        if(save==null)return;save.setEnabled(!saving&&!recognitionPending);save.setText(saving?"保存中…":"保存标记");
        kinds.setEnabled(!recognitionPending);foods.setEnabled(!recognitionPending);kcalLow.setEnabled(!recognitionPending);kcalHigh.setEnabled(!recognitionPending);
        capture.setEnabled(!photoBusy&&!recognitionPending);choose.setEnabled(!photoBusy&&!recognitionPending);
        recognize.setEnabled(!photoBusy&&!recognitionPending&&!photoName.isEmpty());recognize.setText(recognitionPending?"识别中…":recognitionAttempted?"查询识别结果":"识别餐食");
    }
    private void toast(String text) { Toast.makeText(this,text,Toast.LENGTH_LONG).show(); }
    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        try { JSONObject event=draft(false);if(expectedUpdatedAt>0)event.put("updatedAt",expectedUpdatedAt);state.putString("draft",event.toString()); }catch(Exception ignored) { }
        state.putString("photoName",photoName);state.putString("cameraName",cameraName);state.putString("requestId",requestId);state.putBoolean("recognitionPending",recognitionPending);state.putBoolean("recognitionAttempted",recognitionAttempted);
    }
    @Override public void onResume() { super.onResume();active=true;if(recognitionPending&&!requestId.isEmpty()) { pollStarted=System.currentTimeMillis();handler.postDelayed(poll,1000); } }
    @Override public void onPause() { active=false;handler.removeCallbacks(poll);super.onPause(); }
    @Override public void onDestroy() {
        photoGeneration++;handler.removeCallbacksAndMessages(null);if(action!=null)action.cancel();if(photoWork!=null)photoWork.cancel(true);
        if(thumbnail!=null) { photo.setImageDrawable(null);thumbnail.recycle();thumbnail=null; }
        if(isFinishing()) {
            if(!photoName.isEmpty())preparedPhoto().delete();
            if(!cameraName.isEmpty()) { new File(MealPhotoProvider.directory(this),cameraName).delete();try { revokeUriPermission(MealPhotoProvider.uri(this,cameraName),Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION); }catch(SecurityException ignored) { } }
        }
        super.onDestroy();
    }
    private void cleanupOldPhotos() {
        long before=System.currentTimeMillis()-86400000L;
        for(File dir:new File[]{getCacheDir(),MealPhotoProvider.directory(this)}) { File[] files=dir.listFiles();if(files!=null)for(File file:files)if((file.getName().startsWith("meal-")||dir.getName().equals("meal-camera"))&&file.isFile()&&file.lastModified()<before)file.delete(); }
    }
}
