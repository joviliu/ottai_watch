package com.example.redmiwatch6installer.xiaomi;

import android.graphics.Bitmap;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/**
 * Minimal port of Gadgetbridge XiaomiFWHelper watchface parsing (AGPLv3).
 *
 * <p>Supports v2 faces (5A A5 header, used by Redmi Watch 6) and v3 faces.
 * Exposes id, name, preview size and the decoded preview Bitmap for the install UI.
 */
public final class WatchfaceParser {
    /** Redmi Watch 6 screen, from RedmiWatch6Coordinator. */
    public static final int SCREEN_W = 432;
    public static final int SCREEN_H = 514;
    /** Known scaled-down preview size seen on this model. */
    public static final int KNOWN_PREVIEW_W = 259;
    public static final int KNOWN_PREVIEW_H = 308;

    private static final byte[] V3_HEADER = new byte[]{0x00, 0x00, 0x06, 0x07, 0x00, 0x02, 0x00, 0x01};

    public final boolean valid;
    public final boolean watchface;
    public final String id;
    public final String name;
    public final int previewWidth;
    public final int previewHeight;
    private final byte[] fw;

    private WatchfaceParser(byte[] fw, boolean valid, boolean watchface, String id, String name,
                            int previewWidth, int previewHeight) {
        this.fw = fw;
        this.valid = valid;
        this.watchface = watchface;
        this.id = id;
        this.name = name;
        this.previewWidth = previewWidth;
        this.previewHeight = previewHeight;
    }

    public byte[] bytes() {
        return fw;
    }

    public static WatchfaceParser parse(byte[] fw) {
        if (fw == null || fw.length < 100) return invalid(fw);
        WatchfaceParser v2 = parseV2(fw);
        if (v2 != null) return v2;
        WatchfaceParser v3 = parseV3(fw);
        if (v3 != null) return v3;
        return invalid(fw);
    }

    private static WatchfaceParser invalid(byte[] fw) {
        return new WatchfaceParser(fw, false, false, null, null, -1, -1);
    }

    private static String cstr(byte[] d, int off) {
        int end = off;
        while (end < d.length && d[end] != 0) end++;
        if (end <= off) return null;
        return new String(d, off, end - off, StandardCharsets.UTF_8);
    }

    private static int u16(byte[] d, int off) {
        return (d[off] & 0xff) | ((d[off + 1] & 0xff) << 8);
    }

    private static int u32(byte[] d, int off) {
        return (d[off] & 0xff) | ((d[off + 1] & 0xff) << 8)
                | ((d[off + 2] & 0xff) << 16) | ((d[off + 3] & 0xff) << 24);
    }

    private static WatchfaceParser parseV2(byte[] fw) {
        if (fw[0] != (byte) 0x5A || fw[1] != (byte) 0xA5) return null;
        if (fw.length < 0x80) return null;
        String id = cstr(fw, 0x28);
        if (id == null || !id.matches("^\\d+$")) return null;
        String name = cstr(fw, 0x68);
        if (name == null) return null;
        int po = u32(fw, 0x20);
        int pw = -1, ph = -1;
        if (po > 0 && po + 12 <= fw.length) {
            pw = u16(fw, po + 4);
            ph = u16(fw, po + 6);
        }
        return new WatchfaceParser(fw, true, true, id, name, pw, ph);
    }

    private static WatchfaceParser parseV3(byte[] fw) {
        for (int i = 0; i < V3_HEADER.length; i++) {
            if (fw[i] != V3_HEADER[i]) return null;
        }
        int nameLen = fw[20] & 0xff;
        String name = new String(fw, 21, Math.min(nameLen, fw.length - 21), StandardCharsets.UTF_8);
        int po = u32(fw, 89);
        int pw = -1, ph = -1;
        if (po > 0 && po + 9 <= fw.length && fw[po] == 1) {
            pw = u16(fw, po + 5);
            ph = u16(fw, po + 7);
        }
        return new WatchfaceParser(fw, true, true, name, name, pw, ph);
    }

    private int previewOffset() {
        if (fw.length < 0x24 || fw[0] != (byte) 0x5A || fw[1] != (byte) 0xA5) return -1;
        int po = u32(fw, 0x20);
        if (po <= 0 || po + 12 > fw.length) return -1;
        return po;
    }

    /** Decodes the embedded preview, or null if absent/corrupt. */
    public Bitmap preview() {
        if (!valid || !watchface || fw == null) return null;
        int po = previewOffset();
        if (po == -1) return null;
        ByteBuffer bb = ByteBuffer.wrap(fw).order(ByteOrder.LITTLE_ENDIAN);
        bb.position(po);
        int bitmapType = bb.get() & 0xff;
        int compression = bb.get() & 0xff;
        bb.getShort();
        int width = bb.getShort() & 0xffff;
        int height = bb.getShort() & 0xffff;
        int size = bb.getInt();
        if (size <= 0 || po + 12 + size > fw.length) return null;
        byte[] pixels = new byte[size];
        bb.get(pixels);
        if (compression != 0) {
            if (compression == 4) pixels = LvglRle.decompressV2(pixels);
            else if (compression == 8) pixels = LvglRle.decompressV1(pixels);
            else return null;
            if (pixels == null) return null;
        }
        return WatchfaceImageDecoder.decode(pixels, bitmapType, compression == 8, width, height);
    }

    /** Gadgetbridge compatibility rule: exact match, or same aspect ratio within 2%. */
    public String compatibility() {
        if (!valid || !watchface) return "Not a watchface file";
        if (id == null) return "Missing watchface id";
        if (previewWidth <= 0) return "Compatibility unknown (no preview)";
        boolean exact = (previewWidth == SCREEN_W && previewHeight == SCREEN_H)
                || (previewWidth == KNOWN_PREVIEW_W && previewHeight == KNOWN_PREVIEW_H);
        if (exact) return "Resolution matches Redmi Watch 6";
        if (previewWidth > SCREEN_W || previewHeight > SCREEN_H) return "NOT compatible (preview larger than screen)";
        double pr = (double) previewWidth / previewHeight;
        double sr = (double) SCREEN_W / SCREEN_H;
        if (Math.abs(pr / sr - 1) <= 0.02) return "Aspect ratio matches (should install)";
        return "NOT compatible (aspect ratio differs)";
    }

    public boolean compatibleEnoughToInstall() {
        if (!valid || !watchface || id == null) return false;
        if (previewWidth <= 0) return true; // unknown -> allow with warning, like Gadgetbridge
        if ((previewWidth == SCREEN_W && previewHeight == SCREEN_H)
                || (previewWidth == KNOWN_PREVIEW_W && previewHeight == KNOWN_PREVIEW_H)) return true;
        if (previewWidth > SCREEN_W || previewHeight > SCREEN_H) return false;
        double pr = (double) previewWidth / previewHeight;
        double sr = (double) SCREEN_W / SCREEN_H;
        return Math.abs(pr / sr - 1) <= 0.02;
    }
}
