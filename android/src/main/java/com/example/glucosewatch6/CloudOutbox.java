package com.example.glucosewatch6;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

/** Accessed only by CloudSync's single worker. No network operation holds a transaction. */
final class CloudOutbox extends SQLiteOpenHelper {
    static final int MAX_RECORDS = 30000;
    static final class Batch {
        final JSONArray readings = new JSONArray();
        final List<Long> ids = new ArrayList<>();
    }
    CloudOutbox(Context c) { super(c, "ottai-cloud-outbox.sqlite", null, 1); }
    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,source_at INTEGER NOT NULL,value REAL NOT NULL,trend TEXT NOT NULL,historical INTEGER NOT NULL)");
        db.execSQL("CREATE TABLE heads(source_at INTEGER PRIMARY KEY,fingerprint TEXT NOT NULL)");
    }
    @Override public void onUpgrade(SQLiteDatabase db, int old, int next) { throw new IllegalStateException("Unsupported queue version"); }
    void enqueue(Reading r, boolean historical) {
        if (!CloudPolicy.validReading(r,System.currentTimeMillis())) return;
        String trend = r.trend;
        SQLiteDatabase db = getWritableDatabase();
        String fingerprint = CloudPolicy.fingerprint(r);
        db.beginTransaction();
        try {
            try (Cursor old = db.rawQuery("SELECT fingerprint FROM heads WHERE source_at=?", new String[]{Long.toString(r.sourceAt)})) {
                if (old.moveToFirst() && !CloudPolicy.shouldEnqueue(old.getString(0),r,historical)) {
                    db.setTransactionSuccessful(); return;
                }
            }
            if (count() >= MAX_RECORDS) throw new IllegalStateException("待上传队列已满，请先恢复云同步");
            ContentValues event = new ContentValues(); event.put("source_at", r.sourceAt); event.put("value", r.mmol);
            event.put("trend", trend); event.put("historical", historical ? 1 : 0);
            db.insertOrThrow("outbox", null, event);
            ContentValues head = new ContentValues(); head.put("source_at", r.sourceAt); head.put("fingerprint", fingerprint);
            db.insertWithOnConflict("heads", null, head, SQLiteDatabase.CONFLICT_REPLACE);
            db.delete("heads", "source_at<?", new String[]{Long.toString(System.currentTimeMillis()-45L*86400000)});
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }
    Batch batch() throws Exception {
        Batch batch = new Batch();
        try (Cursor rows = getReadableDatabase().rawQuery("SELECT id,source_at,value,trend,historical FROM outbox ORDER BY id LIMIT 96", null)) {
            while (rows.moveToNext()) {
                batch.ids.add(rows.getLong(0));
                batch.readings.put(new JSONObject().put("sourceAt", rows.getLong(1)).put("value", rows.getDouble(2))
                    .put("trend", rows.getString(3)).put("historical", rows.getInt(4)==1));
            }
        }
        return batch;
    }
    void acknowledged(Batch batch) {
        SQLiteDatabase db = getWritableDatabase(); db.beginTransaction();
        try {
            for (long id : batch.ids) db.delete("outbox", "id=?", new String[]{Long.toString(id)});
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }
    int count() {
        try (Cursor c = getReadableDatabase().rawQuery("SELECT count(*) FROM outbox", null)) { c.moveToFirst(); return c.getInt(0); }
    }
    void resetHeads() { getWritableDatabase().delete("heads", null, null); }
}
