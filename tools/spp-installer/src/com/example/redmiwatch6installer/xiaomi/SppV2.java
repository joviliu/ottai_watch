package com.example.redmiwatch6installer.xiaomi;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;

/**
 * Minimal SPP V2 framing (A5 A5 ...), ported from Gadgetbridge XiaomiSppPacketV2 (AGPLv3).
 *
 * <p>Only what the installer needs: session-config request, DATA send/recv, ACK send/wait.
 */
public final class SppV2 {
    public static final byte[] PREAMBLE = new byte[]{(byte) 0xa5, (byte) 0xa5};

    public static final int TYPE_NACK = 0;
    public static final int TYPE_ACK = 1;
    public static final int TYPE_SESSION = 2;
    public static final int TYPE_DATA = 3;

    public static final int RAW_PROTOBUF = 1;
    public static final int RAW_DATA = 2;
    public static final int RAW_ACTIVITY = 5;

    public static final int OP_PLAIN = 1;
    public static final int OP_ENCRYPTED = 2;

    public static final int SESSION_START_REQ = 1;

    private SppV2() {}

    public static int crc16arc(byte[] payload) {
        int crc = 0;
        for (byte b : payload) {
            for (int j = 0; j < 8; j++) {
                crc <<= 1;
                if ((((crc >> 16) & 1) ^ ((b >> j) & 1)) == 1) crc ^= 0x8005;
            }
        }
        return (Integer.reverse(crc) >>> 16) & 0xffff;
    }

    public static byte[] frame(int type, int seq, byte[] payload) {
        ByteBuffer buf = ByteBuffer.allocate(8 + payload.length).order(ByteOrder.LITTLE_ENDIAN);
        buf.put(PREAMBLE);
        buf.put((byte) (type & 0xf));
        buf.put((byte) (seq & 0xff));
        buf.putShort((short) payload.length);
        buf.putShort((short) crc16arc(payload));
        buf.put(payload);
        return buf.array();
    }

    public static byte[] sessionStartRequest(int seq) {
        byte[] payload = new byte[]{
                (byte) SESSION_START_REQ,
                1, 0x03, 0x00, 0x01, 0x00, 0x00,
                2, 0x02, 0x00, 0x00, (byte) 0xfc,
                3, 0x02, 0x00, 0x20, 0x00,
                4, 0x02, 0x00, 0x10, 0x27,
        };
        return frame(TYPE_SESSION, seq, payload);
    }

    public static byte[] ack(int seq) {
        return frame(TYPE_ACK, seq, new byte[0]);
    }

    /** DATA payload: rawChannel(1) + opcode(1) + body (encrypted with CTR for commands). */
    public static byte[] dataPayload(SppPacketV1.Channel channel, byte[] body, XiaomiCrypto.SessionKeys keys,
                                     boolean plaintext) {
        int raw;
        int op;
        if (channel == SppPacketV1.Channel.DATA) {
            raw = RAW_DATA;
            op = OP_PLAIN;
        } else if (plaintext || keys == null) {
            raw = RAW_PROTOBUF;
            op = OP_PLAIN;
        } else {
            raw = RAW_PROTOBUF;
            op = OP_ENCRYPTED;
            body = XiaomiCrypto.ctrCrypt(keys.encKey, body);
        }
        ByteBuffer buf = ByteBuffer.allocate(2 + body.length);
        buf.put((byte) raw);
        buf.put((byte) op);
        buf.put(body);
        return buf.array();
    }

    public static final class Decoded {
        public int type;
        public int seq;
        public byte[] payload;
        public int totalLen;
    }

    public static Decoded decodeOne(byte[] buf, int off, int len) {
        if (len < 8) return null;
        if (buf[off] != PREAMBLE[0] || buf[off + 1] != PREAMBLE[1]) return null;
        int type = buf[off + 2] & 0xf;
        int seq = buf[off + 3] & 0xff;
        int plen = (buf[off + 4] & 0xff) | ((buf[off + 5] & 0xff) << 8);
        int total = 8 + plen;
        if (len < total) return null;
        byte[] payload = Arrays.copyOfRange(buf, off + 8, off + 8 + plen);
        int given = (buf[off + 6] & 0xff) | ((buf[off + 7] & 0xff) << 8);
        if (crc16arc(payload) != given) return null;
        Decoded d = new Decoded();
        d.type = type;
        d.seq = seq;
        d.payload = payload;
        d.totalLen = total;
        return d;
    }
}
