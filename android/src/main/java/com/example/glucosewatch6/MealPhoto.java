package com.example.glucosewatch6;

import android.content.Context;
import android.graphics.*;
import android.media.ExifInterface;
import android.net.Uri;
import java.io.*;
import java.util.*;

final class MealPhoto {
    static byte[] prepare(Context c,Uri uri) throws Exception {
        File input=File.createTempFile("meal-import-",".img",c.getCacheDir());
        Set<Bitmap> images=Collections.newSetFromMap(new IdentityHashMap<Bitmap,Boolean>());
        try {
            try(InputStream source=c.getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(input)) {
                if(source==null)throw new IOException();byte[] buf=new byte[8192];int n,total=0;
                while((n=source.read(buf))!=-1) { total+=n;if(total>20*1024*1024)throw new IOException();out.write(buf,0,n); }
            }
            BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeFile(input.getPath(),options);
            if(options.outWidth<=0||options.outHeight<=0||options.outWidth>40000||options.outHeight>40000||(long)options.outWidth*options.outHeight>200_000_000L)throw new IOException();
            options.inSampleSize=1;
            while(options.outWidth/options.inSampleSize>2048||options.outHeight/options.inSampleSize>2048||(long)(options.outWidth/options.inSampleSize)*(options.outHeight/options.inSampleSize)>4_000_000)options.inSampleSize*=2;
            options.inJustDecodeBounds=false;Bitmap bitmap=BitmapFactory.decodeFile(input.getPath(),options);if(bitmap==null)throw new IOException();images.add(bitmap);
            Matrix matrix=new Matrix();
            try {
                int orientation=new ExifInterface(input.getPath()).getAttributeInt(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_NORMAL);
                switch(orientation) {
                    case ExifInterface.ORIENTATION_FLIP_HORIZONTAL:matrix.setScale(-1,1);break;
                    case ExifInterface.ORIENTATION_ROTATE_180:matrix.setRotate(180);break;
                    case ExifInterface.ORIENTATION_FLIP_VERTICAL:matrix.setScale(1,-1);break;
                    case ExifInterface.ORIENTATION_TRANSPOSE:matrix.setRotate(90);matrix.postScale(-1,1);break;
                    case ExifInterface.ORIENTATION_ROTATE_90:matrix.setRotate(90);break;
                    case ExifInterface.ORIENTATION_TRANSVERSE:matrix.setRotate(-90);matrix.postScale(-1,1);break;
                    case ExifInterface.ORIENTATION_ROTATE_270:matrix.setRotate(-90);break;
                }
            }catch(IOException unsupported) { }
            if(!matrix.isIdentity()) { bitmap=Bitmap.createBitmap(bitmap,0,0,bitmap.getWidth(),bitmap.getHeight(),matrix,true);images.add(bitmap); }
            double scale=Math.min(1,EventPolicy.MAX_IMAGE_EDGE/(double)Math.max(bitmap.getWidth(),bitmap.getHeight()));
            if(scale<1) { bitmap=Bitmap.createScaledBitmap(bitmap,Math.max(1,(int)(bitmap.getWidth()*scale)),Math.max(1,(int)(bitmap.getHeight()*scale)),true);images.add(bitmap); }
            Bitmap opaque=Bitmap.createBitmap(bitmap.getWidth(),bitmap.getHeight(),Bitmap.Config.ARGB_8888);images.add(opaque);Canvas canvas=new Canvas(opaque);canvas.drawColor(Color.WHITE);canvas.drawBitmap(bitmap,0,0,new Paint(Paint.FILTER_BITMAP_FLAG));
            for(int quality:new int[]{85,75,60,45}) {
                ByteArrayOutputStream output=new ByteArrayOutputStream();if(!opaque.compress(Bitmap.CompressFormat.JPEG,quality,output))throw new IOException();
                byte[] bytes=output.toByteArray();if(bytes.length<=EventPolicy.MAX_IMAGE)return bytes;
            }
            throw new IOException();
        } finally { input.delete();for(Bitmap bitmap:images)if(!bitmap.isRecycled())bitmap.recycle(); }
    }
    private MealPhoto() { }
}
