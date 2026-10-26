package com.example.redmiwatch6installer.xiaomi;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;

/**
 * SPP V1 framing (BA DC FE ... EF), ported from Gadgetbridge XiaomiSppPacketV1 (AGPLv3).
 */
public final class SppPacketV1 {
    public static final byte[] PREAMBLE = new byte[]{(byte) 0xba, (byte) 0xdc, (byte) 0xfe};
    public static final byte EPILOGUE = (byte) 0xef;

    public static final int RAW_VERSION = 0;
    public static final int RAW_PROTO_RX = 1;
    public static final int RAW_PROTO_TX = 2;
    public static final int RAW_FITNESS = 3;
    public static final int RAW_MASS = 5;

    public static final int DATA_PLAIN = 0;
    public static final int DATA_ENCRYPTED = 1;
    public static final int DATA_AUTH = 2;

    public static final int OP_READ = 0;
    public static final int OP_SEND = 2;

    public enum Channel { VERSION, COMMAND, DATA, ACTIVITY, UNKNOWN }

    public final Channel channel;
    public final int dataType;
    public final byte[] payload;

    public SppPacketV1(Channel channel, int dataType, byte[] payload) {
        this.channel = channel;
        this.dataType = dataType;
        this.payload = payload;
    }

    public static int rawFor(Channel c) {
        switch (c) {
            case VERSION: return RAW_VERSION;
            case COMMAND: return RAW_PROTO_TX;
            case DATA: return RAW_MASS;
            case ACTIVITY: return RAW_FITNESS;
            default: return -1;
        }
    }

    public static Channel fromRaw(int raw) {
        if (raw == RAW_VERSION) return Channel.VERSION;
        if (raw == RAW_PROTO_RX || raw == RAW_PROTO_TX) return Channel.COMMAND;
        if (raw == RAW_FITNESS) return Channel.ACTIVITY;
        if (raw == RAW_MASS) return Channel.DATA;
        return Channel.UNKNOWN;
    }

    /** Encode one frame. For COMMAND+ENCRYPTED the counter prefix is added (Gadgetbridge behavior). */
    public static byte[] encode(Channel channel, int dataType, int opCode, int frameSerial,
                                boolean needsResponse, byte[] payload,
                                XiaomiCrypto.SessionKeys keys, int encCounter) {
        byte[] body = payload;
        if (dataType == DATA_ENCRYPTED && keys != null) {
            if (channel == Channel.COMMAND) {
                byte[] enc = XiaomiCrypto.encryptV1(keys.encKey, keys.encNonce, encCounter, payload);
                body = ByteBuffer.allocate(2 + enc.length).order(ByteOrder.LITTLE_ENDIAN)
                        .putShort((short) encCounter).put(enc).array();
            } else {
                body = XiaomiCrypto.encryptV1(keys.encKey, keys.encNonce, 0, payload);
            }
        }
        ByteBuffer buf = ByteBuffer.allocate(11 + body.length).order(ByteOrder.LITTLE_ENDIAN);
        buf.put(PREAMBLE);
        buf.put((byte) (rawFor(channel) & 0xf));
        buf.put((byte) (0x80 | (needsResponse ? 0x40 : 0)));
        buf.putShort((short) (body.length + 3));
        buf.put((byte) opCode);
        buf.put((byte) frameSerial);
        buf.put((byte) dataType);
        buf.put(body);
        buf.put(EPILOGUE);
        return buf.array();
    }

    public static final class Decoded {
        public Channel channel;
        public int dataType;
        public byte[] payload;
        public int totalLen;
    }

    /** Try to decode one packet at offset 0. Returns null if incomplete/invalid. */
    public static Decoded decodeOne(byte[] buf, int off, int len) {
        if (len < 11) return null;
        if (buf[off] != PREAMBLE[0] || buf[off + 1] != PREAMBLE[1] || buf[off + 2] != PREAMBLE[2]) return null;
        int raw = buf[off + 3] & 0xff;
        int sizeField = ((buf[off + 5] & 0xff)) | ((buf[off + 6] & 0xff) << 8);
        int total = sizeField + 8;
        if (len < total) return null;
        if (buf[off + total - 1] != EPILOGUE) return null;
        int dataType = buf[off + 9] & 0xff;
        int payloadLen = sizeField - 3;
        byte[] payload = Arrays.copyOfRange(buf, off + 10, off + 10 + payloadLen);
        Decoded d = new Decoded();
        d.channel = fromRaw(raw & 0xf);
        d.dataType = dataType;
        d.payload = payload;
        d.totalLen = total;
        return d;
    }

    /** Version request frame: BA DC FE 00 C0 03 00 00 00 00 EF */
    public static byte[] versionRequest() {
        return new byte[]{(byte) 0xba, (byte) 0xdc, (byte) 0xfe, 0x00, (byte) 0xc0,
                0x03, 0x00, 0x00, 0x00, 0x00, (byte) 0xef};
    }
}
