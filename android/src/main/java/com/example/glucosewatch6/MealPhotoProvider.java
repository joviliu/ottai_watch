package com.example.glucosewatch6;

import android.content.*;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;

/** A grant-only camera destination; no general filesystem paths are exposed. */
public final class MealPhotoProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    static File directory(Context c) { File dir=new File(c.getCacheDir(),"meal-camera");dir.mkdirs();return dir; }
    static Uri uri(Context c,String name) { return Uri.parse("content://"+c.getPackageName()+".mealphoto/capture/"+name); }
    private File file(Uri uri) throws FileNotFoundException {
        if(uri.getPathSegments().size()!=2||!"capture".equals(uri.getPathSegments().get(0)))throw new FileNotFoundException();
        String name=uri.getLastPathSegment();if(name==null||!name.matches("[a-f0-9-]{36}\\.jpg"))throw new FileNotFoundException();
        return new File(directory(getContext()),name);
    }
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        File target=file(uri);int flags;
        if("r".equals(mode))flags=ParcelFileDescriptor.MODE_READ_ONLY;
        else if("w".equals(mode)||"wt".equals(mode))flags=ParcelFileDescriptor.MODE_WRITE_ONLY|ParcelFileDescriptor.MODE_CREATE|ParcelFileDescriptor.MODE_TRUNCATE;
        else if("rw".equals(mode)||"rwt".equals(mode))flags=ParcelFileDescriptor.MODE_READ_WRITE|ParcelFileDescriptor.MODE_CREATE|("rwt".equals(mode)?ParcelFileDescriptor.MODE_TRUNCATE:0);
        else throw new FileNotFoundException();
        return ParcelFileDescriptor.open(target,flags);
    }
    @Override public String getType(Uri uri) { return "image/jpeg"; }
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order) {
        try { File file=file(uri);MatrixCursor result=new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE});result.addRow(new Object[]{"meal-photo.jpg",file.length()});return result; }
        catch(FileNotFoundException e) { return null; }
    }
    @Override public Uri insert(Uri uri,ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri,ContentValues values,String selection,String[] args) { return 0; }
    @Override public int delete(Uri uri,String selection,String[] args) { return 0; }
}
