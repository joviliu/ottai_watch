package com.example.redmiwatch6installer.xiaomi;

import android.graphics.Bitmap;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * Decodes raw watchface preview pixels into a Bitmap.
 * Ported from Gadgetbridge XiaomiBitmapUtils.decodeWatchfaceImage (AGPLv3).
 */
public final class WatchfaceImageDecoder {
    private WatchfaceImageDecoder() {}

    private static int rgb565ToRgb888(short value) {
        int c = value & 0xffff;
        return ((c & 0xf800) << 8) | ((c & 0x07e0) << 5) | ((c & 0x001f) << 3);
    }

    /**
     * @param bitmapFormat  value from preview header (0 = ARGB8888, 1/3/4/7 = RGB565 variants,
     *                     6 = RGB565+alpha, 16 = 8-bit palette)
     * @param swapRedBlue  true when compressionType == 8 (matches Gadgetbridge behavior)
     */
    public static Bitmap decode(byte[] data, int bitmapFormat, boolean swapRedBlue, int width, int height) {
        int expected;
        switch (bitmapFormat) {
            case 0: expected = width * height * 4; break;
            case 1: case 3: case 4: case 7: expected = width * height * 2; break;
            case 6: expected = width * height * 3; break;
            case 16: expected = 256 * 4 + width * height; break;
            default: return null;
        }
        if (expected > data.length) return null;

        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        ByteBuffer bb = ByteBuffer.wrap(data);
        bb.order(bitmapFormat == 7 ? ByteOrder.BIG_ENDIAN : ByteOrder.LITTLE_ENDIAN);

        int[] palette = new int[0];
        if (bitmapFormat == 16) {
            palette = new int[256];
            for (int i = 0; i < 256; i++) palette[i] = bb.getInt();
        }
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                switch (bitmapFormat) {
                    case 0x00:
                        bitmap.setPixel(x, y, bb.getInt());
                        break;
                    case 0x01: case 0x03: case 0x04: case 0x07:
                        bitmap.setPixel(x, y, 0xff000000 | rgb565ToRgb888(bb.getShort()));
                        break;
                    case 0x06: {
                        int rgb = rgb565ToRgb888(bb.getShort());
                        int alpha = bb.get() & 0xff;
                        bitmap.setPixel(x, y, (alpha << 24) | rgb);
                        break;
                    }
                    case 0x10: {
                        int id = bb.get() & 0xff;
                        bitmap.setPixel(x, y, palette[id]);
                        break;
                    }
                }
            }
        }
        return bitmap;
    }
}
