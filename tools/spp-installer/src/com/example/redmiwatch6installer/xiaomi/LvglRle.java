package com.example.redmiwatch6installer.xiaomi;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * LVGL RLE decompression, ported from Gadgetbridge XiaomiBitmapUtils
 * (AGPLv3, (C) 2024 Yoran Vulker).
 */
public final class LvglRle {
    private static final byte[] HEADER = new byte[]{(byte) 0xe0, 0x21, (byte) 0xa5, 0x5a};

    private LvglRle() {}

    private static boolean hasHeader(byte[] d) {
        return d.length >= 4 && d[0] == HEADER[0] && d[1] == HEADER[1] && d[2] == HEADER[2] && d[3] == HEADER[3];
    }

    /** compressionType 8 in the watchface header. */
    public static byte[] decompressV1(byte[] in) {
        if (!hasHeader(in)) return null;
        int chunkSize = in[4] & 0xf;
        if (chunkSize == 0) chunkSize = 1;
        ByteBuffer bb = ByteBuffer.wrap(in).order(ByteOrder.LITTLE_ENDIAN);
        bb.getInt();
        int outSize = (bb.getInt() >> 4) & 0xfffffff;
        byte[] out = new byte[outSize];
        int off = 0;
        while (bb.hasRemaining()) {
            int control = bb.get() & 0xff;
            int n = control & 0x7f;
            if (off + chunkSize * (n + 1) > out.length) return null;
            if ((control & 0x80) != 0) {
                if (bb.remaining() < chunkSize) return null;
                byte[] chunk = new byte[chunkSize];
                bb.get(chunk);
                for (int i = 0; i < n + 1; i++) {
                    System.arraycopy(chunk, 0, out, off, chunk.length);
                    off += chunk.length;
                }
            } else {
                if (bb.remaining() < chunkSize * (n + 1)) return null;
                byte[] chunk = new byte[chunkSize * (n + 1)];
                bb.get(chunk);
                System.arraycopy(chunk, 0, out, off, chunk.length);
                off += chunk.length;
            }
        }
        return out;
    }

    /** compressionType 4 in the watchface header. */
    public static byte[] decompressV2(byte[] in) {
        if (!hasHeader(in)) return null;
        int chunkSize = in[4] & 0xf;
        if (chunkSize == 0) chunkSize = 1;
        ByteBuffer bb = ByteBuffer.wrap(in).order(ByteOrder.LITTLE_ENDIAN);
        bb.getInt();
        int outSize = (bb.getInt() >> 4) & 0xfffffff;
        byte[] out = new byte[outSize];
        int off = 0;
        while (bb.hasRemaining()) {
            int control = bb.get() & 0xff;
            int n = control & 0x7f;
            if (off + chunkSize * n > out.length) return null;
            if ((control & 0x80) != 0) {
                if (bb.remaining() < chunkSize * n) return null;
                byte[] chunk = new byte[chunkSize * n];
                bb.get(chunk);
                System.arraycopy(chunk, 0, out, off, chunk.length);
                off += chunk.length;
            } else {
                if (bb.remaining() < chunkSize) return null;
                byte[] chunk = new byte[chunkSize];
                bb.get(chunk);
                for (int i = 0; i < n; i++) {
                    System.arraycopy(chunk, 0, out, off, chunk.length);
                    off += chunk.length;
                }
            }
        }
        return out;
    }
}
