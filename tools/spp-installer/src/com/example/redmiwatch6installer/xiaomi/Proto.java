package com.example.redmiwatch6installer.xiaomi;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Minimal protobuf (proto2) encoder/decoder for the tiny subset of xiaomi.proto
 * needed for auth + watchface install + data upload.
 *
 * <p>Field numbers mirror GBProtobufGenerator/src/main/proto/xiaomi*.proto in Gadgetbridge.
 */
public final class Proto {
    private Proto() {}

    public static final class Field {
        public final int number;
        public final int wire; // 0 varint, 1 fixed64, 2 delimited, 5 fixed32
        public final long varint;
        public final byte[] bytes;
        Field(int number, int wire, long varint, byte[] bytes) {
            this.number = number; this.wire = wire; this.varint = varint; this.bytes = bytes;
        }
    }

    public static List<Field> parse(byte[] buf) {
        return parse(buf, 0, buf.length);
    }

    public static List<Field> parse(byte[] buf, int off, int len) {
        List<Field> out = new ArrayList<>();
        int pos = off, end = off + len;
        while (pos < end) {
            long key = readVarint(buf, pos);
            int keyLen = varintLen(buf, pos);
            pos += keyLen;
            int number = (int) (key >>> 3);
            int wire = (int) (key & 7);
            if (wire == 0) {
                long v = readVarint(buf, pos);
                pos += varintLen(buf, pos);
                out.add(new Field(number, wire, v, null));
            } else if (wire == 1) {
                pos += 8;
                out.add(new Field(number, wire, 0, null));
            } else if (wire == 2) {
                long n = readVarint(buf, pos);
                pos += varintLen(buf, pos);
                byte[] b = new byte[(int) n];
                System.arraycopy(buf, pos, b, 0, (int) n);
                pos += n;
                out.add(new Field(number, wire, 0, b));
            } else if (wire == 5) {
                pos += 4;
                out.add(new Field(number, wire, 0, null));
            } else {
                throw new IllegalArgumentException("unsupported wire type " + wire);
            }
        }
        return out;
    }

    public static Field first(List<Field> fields, int number) {
        for (Field f : fields) if (f.number == number) return f;
        return null;
    }

    private static long readVarint(byte[] buf, int pos) {
        long res = 0;
        int shift = 0;
        while (true) {
            int b = buf[pos++] & 0xff;
            res |= (long) (b & 0x7f) << shift;
            if ((b & 0x80) == 0) break;
            shift += 7;
        }
        return res;
    }

    private static int varintLen(byte[] buf, int pos) {
        int n = 0;
        while (((buf[pos++] & 0x80) != 0)) n++;
        return n + 1;
    }

    // ---- encoding ----
    public static final class Writer {
        private final ByteArrayOutputStream os = new ByteArrayOutputStream();
        public Writer u32(int field, long value) {
            key(field, 0);
            varint(value);
            return this;
        }
        public Writer bytes(int field, byte[] value) {
            if (value == null) return this;
            key(field, 2);
            varint(value.length);
            os.write(value, 0, value.length);
            return this;
        }
        public Writer string(int field, String value) {
            if (value == null) return this;
            return bytes(field, value.getBytes(StandardCharsets.UTF_8));
        }
        public Writer msg(int field, byte[] value) {
            return bytes(field, value);
        }
        public Writer msg(int field, Writer nested) {
            if (nested == null) return this;
            return bytes(field, nested.build());
        }
        public Writer f32float(int field, float value) {
            key(field, 5);
            int bits = Float.floatToRawIntBits(value);
            os.write(bits & 0xff);
            os.write((bits >> 8) & 0xff);
            os.write((bits >> 16) & 0xff);
            os.write((bits >> 24) & 0xff);
            return this;
        }
        private void key(int field, int wire) {
            varint(((long) field << 3) | wire);
        }
        private void varint(long v) {
            while (true) {
                if ((v & ~0x7FL) == 0) {
                    os.write((int) v);
                    return;
                }
                os.write(((int) v & 0x7f) | 0x80);
                v >>>= 7;
            }
        }
        public byte[] build() {
            return os.toByteArray();
        }
    }

    // ---- high-level builders (mirrors xiaomi.proto) ----
    /** Command{1:type, 2:subtype, 3:auth, 6:watchface, 24:dataUpload} */
    public static byte[] command(int type, Integer subtype, byte[] auth, byte[] watchface, byte[] dataUpload) {
        Writer w = new Writer().u32(1, type);
        if (subtype != null) w.u32(2, subtype);
        if (auth != null) w.msg(3, auth);
        if (watchface != null) w.msg(6, watchface);
        if (dataUpload != null) w.msg(24, dataUpload);
        return w.build();
    }

    /** Account: 30=appVerify, 31=deviceVerify, 32=appConfirm */
    public static byte[] appVerify(byte[] phoneNonce, String deviceId) {
        Writer inner = new Writer().bytes(1, phoneNonce);
        if (deviceId != null && !deviceId.isEmpty()) inner.string(2, deviceId);
        return new Writer().msg(30, inner).build();
    }

    public static byte[] appConfirm(byte[] encryptedNonces, byte[] encryptedDeviceInfo) {
        Writer inner = new Writer().bytes(1, encryptedNonces).bytes(2, encryptedDeviceInfo);
        return new Writer().msg(32, inner).build();
    }

    public static byte[] companionDevice(int apiLevel, String model, String region) {
        return new Writer()
                .u32(1, 0)
                .f32float(2, (float) apiLevel)
                .string(3, model)
                .u32(4, 224)
                .string(5, region)
                .build();
    }

    /** Watchface{6: installStart{id:1, size:2}} */
    public static byte[] watchfaceInstallStart(String id, int size) {
        byte[] start = new Writer().string(1, id).u32(2, size).build();
        return new Writer().msg(6, start).build();
    }

    /** DataUpload{1: request{1:type, 2:md5, 3:size}} */
    public static byte[] dataUploadRequest(int type, byte[] md5, int size) {
        byte[] req = new Writer().u32(1, type).bytes(2, md5).u32(3, size).build();
        return new Writer().msg(1, req).build();
    }

    // ---- high-level parsing ----
    public static final class Command {
        public int type;
        public int subtype;
        public byte[] auth;
        public byte[] watchface;
        public byte[] dataUpload;
        public long status;
        public boolean hasStatus;
    }

    public static Command parseCommand(byte[] buf) {
        Command c = new Command();
        for (Field f : parse(buf)) {
            if (f.number == 1) c.type = (int) f.varint;
            else if (f.number == 2) c.subtype = (int) f.varint;
            else if (f.number == 3) c.auth = f.bytes;
            else if (f.number == 6) c.watchface = f.bytes;
            else if (f.number == 24) c.dataUpload = f.bytes;
            else if (f.number == 100) { c.status = f.varint; c.hasStatus = true; }
        }
        return c;
    }

    public static final class DeviceVerify {
        public byte[] nonce;
        public byte[] hmac;
    }

    /** Account message -> deviceVerify (field 31) or status (field 8). */
    public static DeviceVerify parseDeviceVerify(byte[] auth) {
        if (auth == null) return null;
        for (Field f : parse(auth)) {
            if (f.number == 31 && f.bytes != null) {
                DeviceVerify dv = new DeviceVerify();
                for (Field g : parse(f.bytes)) {
                    if (g.number == 1) dv.nonce = g.bytes;
                    else if (g.number == 2) dv.hmac = g.bytes;
                }
                return dv;
            }
        }
        return null;
    }

    public static Long parseAuthStatus(byte[] auth) {
        if (auth == null) return null;
        for (Field f : parse(auth)) {
            if (f.number == 8) return f.varint;
        }
        return null;
    }

    public static Long parseInstallStatus(byte[] watchface) {
        if (watchface == null) return null;
        for (Field f : parse(watchface)) {
            if (f.number == 5) return f.varint;
        }
        return null;
    }

    public static final class FaceInfo {
        public String id;
        public String name;
        public boolean active;
        public boolean canDelete;
    }

    /** Watchface{1: WatchfaceList{1: repeated WatchfaceInfo}} */
    public static java.util.List<FaceInfo> parseFaceList(byte[] watchface) {
        java.util.List<FaceInfo> out = new java.util.ArrayList<>();
        if (watchface == null) return out;
        for (Field f : parse(watchface)) {
            if (f.number == 1 && f.bytes != null) {
                for (Field g : parse(f.bytes)) {
                    if (g.number == 1 && g.bytes != null) {
                        FaceInfo fi = new FaceInfo();
                        for (Field h : parse(g.bytes)) {
                            if (h.number == 1 && h.bytes != null) {
                                fi.id = new String(h.bytes, StandardCharsets.UTF_8);
                            } else if (h.number == 2 && h.bytes != null) {
                                fi.name = new String(h.bytes, StandardCharsets.UTF_8);
                            } else if (h.number == 3) {
                                fi.active = h.varint != 0;
                            } else if (h.number == 4) {
                                fi.canDelete = h.varint != 0;
                            }
                        }
                        if (fi.id != null) out.add(fi);
                    }
                }
            }
        }
        return out;
    }

    /** Watchface{2: watchfaceId} for set/delete. */
    public static byte[] watchfaceId(String id) {
        return new Writer().string(2, id).build();
    }

    public static final class UploadAck {
        public long errno;
        public long resumePosition;
        public long chunkSize;
        public boolean hasChunkSize;
    }

    public static UploadAck parseUploadAck(byte[] dataUpload) {
        if (dataUpload == null) return null;
        for (Field f : parse(dataUpload)) {
            if (f.number == 2 && f.bytes != null) {
                UploadAck ack = new UploadAck();
                for (Field g : parse(f.bytes)) {
                    if (g.number == 2) ack.errno = g.varint;
                    else if (g.number == 4) ack.resumePosition = g.varint;
                    else if (g.number == 5) { ack.chunkSize = g.varint; ack.hasChunkSize = true; }
                }
                return ack;
            }
        }
        return null;
    }

    public static void writeU16LE(byte[] dst, int off, int v) {
        dst[off] = (byte) (v & 0xff);
        dst[off + 1] = (byte) ((v >> 8) & 0xff);
    }

    public static void writeU32LE(byte[] dst, int off, long v) {
        dst[off] = (byte) (v & 0xff);
        dst[off + 1] = (byte) ((v >> 8) & 0xff);
        dst[off + 2] = (byte) ((v >> 16) & 0xff);
        dst[off + 3] = (byte) ((v >> 24) & 0xff);
    }
}
