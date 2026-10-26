package com.example.redmiwatch6installer.xiaomi;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.zip.CRC32;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.bouncycastle.crypto.engines.AESEngine;
import org.bouncycastle.crypto.modes.CCMBlockCipher;
import org.bouncycastle.crypto.params.AEADParameters;
import org.bouncycastle.crypto.params.KeyParameter;

/**
 * Crypto for the Xiaomi protobuf handshake + SPP V1/V2 transport.
 * Logic ported from Gadgetbridge XiaomiAuthService (AGPLv3).
 */
public final class XiaomiCrypto {
    private XiaomiCrypto() {}

    public static byte[] hexToBytes(String hex) {
        String h = hex.trim();
        if (h.startsWith("0x") || h.startsWith("0X")) h = h.substring(2);
        h = h.replaceAll("\\s", "");
        byte[] out = new byte[h.length() / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(h.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    public static String bytesToHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte v : b) sb.append(String.format("%02x", v));
        return sb.toString();
    }

    public static byte[] randomNonce() {
        byte[] n = new byte[16];
        new SecureRandom().nextBytes(n);
        return n;
    }

    public static byte[] hmacSha256(byte[] key, byte[] input) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(input);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static byte[] concat(byte[]... parts) {
        int n = 0;
        for (byte[] p : parts) n += p.length;
        byte[] out = new byte[n];
        int o = 0;
        for (byte[] p : parts) {
            System.arraycopy(p, 0, out, o, p.length);
            o += p.length;
        }
        return out;
    }

    /**
     * HKDF-expand style derivation from Gadgetbridge computeAuthStep3Hmac.
     * Returns 64 bytes: [decKey(16), encKey(16), decNonce(4), encNonce(4), ...].
     */
    public static byte[] computeStep3(byte[] secretKey, byte[] phoneNonce, byte[] watchNonce) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(concat(phoneNonce, watchNonce), "HmacSHA256"));
            byte[] prk = mac.doFinal(secretKey);
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            byte[] info = "miwear-auth".getBytes();
            byte[] out = new byte[64];
            byte[] tmp = new byte[0];
            byte b = 1;
            int i = 0;
            while (i < out.length) {
                mac.update(tmp);
                mac.update(info);
                mac.update(b);
                tmp = mac.doFinal();
                for (int j = 0; j < tmp.length && i < out.length; j++, i++) out[i] = tmp[j];
                b++;
            }
            return out;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    public static final class SessionKeys {
        public final byte[] encKey = new byte[16];
        public final byte[] decKey = new byte[16];
        public final byte[] encNonce = new byte[4];
        public final byte[] decNonce = new byte[4];
    }

    public static SessionKeys derive(byte[] secret, byte[] phoneNonce, byte[] watchNonce,
                                     byte[] watchHmac) {
        byte[] step3 = computeStep3(secret, phoneNonce, watchNonce);
        SessionKeys k = new SessionKeys();
        System.arraycopy(step3, 16, k.encKey, 0, 16);
        System.arraycopy(step3, 0, k.decKey, 0, 16);
        System.arraycopy(step3, 32, k.decNonce, 0, 4);
        System.arraycopy(step3, 36, k.encNonce, 0, 4);
        // verify watch HMAC like Gadgetbridge does
        byte[] confirm = hmacSha256(k.decKey, concat(watchNonce, phoneNonce));
        // caller checks; keep constant-time-ish compare
        if (!MessageDigest.isEqual(confirm, watchHmac)) {
            throw new SecurityException("Watch HMAC mismatch - wrong auth key?");
        }
        return k;
    }

    private static byte[] nonce12(byte[] nonce4, int counter) {
        return ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN)
                .put(nonce4).putInt(0).putInt(counter).array();
    }

    /** AES-CCM encrypt with 4-byte tag (matches Gadgetbridge encrypt()). */
    public static byte[] encryptV1(byte[] key, byte[] nonce4, int counter, byte[] plain) {
        try {
            CCMBlockCipher cipher = new CCMBlockCipher(new AESEngine());
            cipher.init(true, new AEADParameters(new KeyParameter(key), 32,
                    nonce12(nonce4, counter), null));
            byte[] out = new byte[cipher.getOutputSize(plain.length)];
            int n = cipher.processBytes(plain, 0, plain.length, out, 0);
            cipher.doFinal(out, n);
            return out;
        } catch (Exception e) {
            throw new RuntimeException("CCM encrypt failed", e);
        }
    }

    /** AES-CCM decrypt with fixed counter 0 (matches Gadgetbridge decrypt()). */
    public static byte[] decryptV1(byte[] key, byte[] nonce4, byte[] cipherText) {
        try {
            CCMBlockCipher cipher = new CCMBlockCipher(new AESEngine());
            cipher.init(false, new AEADParameters(new KeyParameter(key), 32,
                    nonce12(nonce4, 0), null));
            byte[] out = new byte[cipher.getOutputSize(cipherText.length)];
            int n = cipher.processBytes(cipherText, 0, cipherText.length, out, 0);
            int m = cipher.doFinal(out, n);
            return Arrays.copyOf(out, n + m);
        } catch (Exception e) {
            throw new RuntimeException("CCM decrypt failed", e);
        }
    }

    /** AES-CTR with key as IV (yes, really - matches Gadgetbridge encryptV2). */
    public static byte[] ctrCrypt(byte[] key, byte[] message) {
        try {
            Cipher cipher = Cipher.getInstance("AES/CTR/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new IvParameterSpec(key));
            return cipher.doFinal(message);
        } catch (Exception e) {
            throw new RuntimeException("CTR crypt failed", e);
        }
    }

    public static byte[] md5(byte[] data) {
        try {
            return MessageDigest.getInstance("MD5").digest(data);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    public static long crc32(byte[] data) {
        CRC32 crc = new CRC32();
        crc.update(data);
        return crc.getValue();
    }
}
