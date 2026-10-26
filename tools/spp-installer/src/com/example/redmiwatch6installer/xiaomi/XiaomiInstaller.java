package com.example.redmiwatch6installer.xiaomi;

import android.os.Build;
import android.util.Log;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Install flow for Redmi Watch 6 over SPP, mirroring Gadgetbridge:
 * version -&gt; auth (type 1) -&gt; watchface install start (type 4/4) -&gt;
 * data upload request (type 22/0) -&gt; chunked upload -&gt; set watchface.
 *
 * <p>Derived from Gadgetbridge XiaomiAuthService, XiaomiWatchfaceService and
 * XiaomiDataUploadService (AGPLv3).
 */
public final class XiaomiInstaller {
    private static final String TAG = "XiaomiInstaller";

    public static final int TYPE_WATCHFACE_FILE = 16;

    public interface Progress {
        void log(String msg);
        void progress(int percent);
    }

    private final SppConnection conn;
    private final Progress progress;
    private final BlockingQueue<byte[]> commands = new LinkedBlockingQueue<>();
    private volatile int sppVersion = -1;

    public XiaomiInstaller(SppConnection conn, Progress progress) {
        this.conn = conn;
        this.progress = progress;
    }

    public void onPacket(byte[] plainOrSentinel) {
        if (plainOrSentinel.length == 2 && (plainOrSentinel[0] & 0xff) == 0xFE) {
            sppVersion = plainOrSentinel[1] & 0xff;
            return;
        }
        commands.offer(plainOrSentinel);
    }

    private byte[] nextCommand(long timeoutMs, String what) throws Exception {
        byte[] c = commands.poll(timeoutMs, TimeUnit.MILLISECONDS);
        if (c == null) throw new Exception("Timeout waiting for " + what);
        return c;
    }

    /** Waits for a command of the given type, logging (not failing on) interleaved packets. */
    private byte[] nextCommandOfType(int type, long timeoutMs, String what) throws Exception {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (true) {
            long wait = deadline - System.currentTimeMillis();
            if (wait <= 0) throw new Exception("Timeout waiting for " + what);
            byte[] c = commands.poll(wait, TimeUnit.MILLISECONDS);
            if (c == null) throw new Exception("Timeout waiting for " + what);
            Proto.Command cmd;
            try {
                cmd = Proto.parseCommand(c);
            } catch (Exception e) {
                progress.log("Skip unparsable packet (" + c.length + "B): " + e.getMessage());
                continue;
            }
            if (cmd.type != type) {
                progress.log("Skip interleaved cmd type=" + cmd.type + " subtype=" + cmd.subtype
                        + " (" + c.length + "B): " + hexSnippet(c));
                continue;
            }
            return c;
        }
    }

    private static String hexSnippet(byte[] c) {
        StringBuilder sb = new StringBuilder();
        int n = Math.min(c.length, 48);
        for (int i = 0; i < n; i++) sb.append(String.format("%02x", c[i]));
        if (c.length > n) sb.append("…");
        return sb.toString();
    }

    private void clearCommands() {
        commands.clear();
    }

    /**
     * Full install. Must run on a background thread.
     *
     * @param authKeyHex 16-byte hex secret (32 hex chars, entered by the user)
     * @param face      parsed watchface (bytes used for upload)
     */
    public void install(String authKeyHex, WatchfaceParser face) throws Exception {
        authenticate(authKeyHex);
        installFace(face);
    }

    /** Steps 1-5: version handshake + authentication. Safe to call once per connection. */
    public void authenticate(String authKeyHex) throws Exception {
        byte[] secret = XiaomiCrypto.hexToBytes(authKeyHex);
        if (secret.length != 16) throw new Exception("Auth key must be 16 bytes hex (32 chars)");

        // 1. version
        progress.log("Requesting SPP version…");
        clearCommands();
        conn.sendVersionRequest();
        // version arrives via sentinel, not the command queue; wait for it
        long t0 = System.currentTimeMillis();
        while (sppVersion < 0 && System.currentTimeMillis() - t0 < 8000) Thread.sleep(100);
        if (sppVersion < 0) {
            progress.log("No version reply, assuming V1");
            sppVersion = 1;
        } else {
            progress.log("SPP version: " + sppVersion);
        }
        if (sppVersion >= 2) {
            progress.log("Upgrading to SPP V2…");
            conn.upgradeToV2AndStartSession();
        }

        // 2. auth step 1: phone nonce (plaintext, DATA_AUTH)
        byte[] phoneNonce = XiaomiCrypto.randomNonce();
        progress.log("Auth step 1 (nonce " + XiaomiCrypto.bytesToHex(phoneNonce).substring(0, 8) + "…)");
        clearCommands();
        conn.sendAuthCommand(Proto.command(1, 26, Proto.appVerify(phoneNonce, ""), null, null));

        // 3. auth step 2: watch nonce + hmac
        byte[] resp = nextCommandOfType(1, 15000, "watch nonce");
        Proto.Command cmd = Proto.parseCommand(resp);
        if (cmd.type != 1 || cmd.auth == null) throw new Exception("Unexpected auth reply type=" + cmd.type);
        Proto.DeviceVerify dv = Proto.parseDeviceVerify(cmd.auth);
        if (dv == null || dv.nonce == null) throw new Exception("No device nonce (wrong key or watch refused)");
        progress.log("Got watch nonce, deriving keys…");
        XiaomiCrypto.SessionKeys keys;
        try {
            keys = XiaomiCrypto.derive(secret, phoneNonce, dv.nonce, dv.hmac);
        } catch (SecurityException e) {
            throw new Exception("Auth key rejected (HMAC mismatch)");
        }
        conn.setKeys(keys);

        // 4. auth step 3: app confirm (still DATA_AUTH / plaintext framing, encrypted content inside)
        byte[] encNonces = XiaomiCrypto.hmacSha256(keys.encKey, concat(phoneNonce, dv.nonce));
        String region = Locale.getDefault().getLanguage().toUpperCase(Locale.ROOT);
        if (region.length() != 2) region = "US";
        byte[] devInfo = Proto.companionDevice(Build.VERSION.SDK_INT, Build.MODEL, region);
        byte[] encDevInfo = XiaomiCrypto.encryptV1(keys.encKey, keys.encNonce, 0, devInfo);
        progress.log("Auth step 3 (confirm)…");
        clearCommands();
        conn.sendAuthCommand(Proto.command(1, 27,
                Proto.appConfirm(encNonces, encDevInfo), null, null));

        // 5. auth result
        resp = nextCommandOfType(1, 15000, "auth result");
        cmd = Proto.parseCommand(resp);
        boolean ok = (cmd.type == 1 && cmd.subtype == 27)
                || (cmd.type == 1 && cmd.auth != null && Long.valueOf(1).equals(Proto.parseAuthStatus(cmd.auth)));
        if (!ok) throw new Exception("Authentication failed (type=" + cmd.type + " subtype=" + cmd.subtype + ")");
        progress.log("Authenticated, channel encrypted");
    }

    /** Steps 6-9: install + upload + activate. Requires an authenticated connection. */
    public void installFace(WatchfaceParser face) throws Exception {
        if (!face.valid || !face.watchface || face.id == null) throw new Exception("Invalid watchface file");
        byte[] fwBytes = face.bytes();
        progress.log("Install start: id=" + face.id + " size=" + fwBytes.length);
        clearCommands();
        conn.sendCommand(Proto.command(4, 4, null, Proto.watchfaceInstallStart(face.id, fwBytes.length), null));
        byte[] resp = nextCommandOfType(4, 15000, "install ack");
        Proto.Command cmd = Proto.parseCommand(resp);
        Long st = Proto.parseInstallStatus(cmd.watchface);
        progress.log("Install reply: subtype=" + cmd.subtype + " status=" + st + " raw=" + hexSnippet(resp));
        if (st == null) throw new Exception("Unexpected install reply");
        if (st != 0) throw new Exception("Watch refused install (status=" + st + ", maybe already installed)");
        progress.log("Watch ready, requesting upload…");

        // 7. data upload request (type 22 subtype 0)
        byte[] md5 = XiaomiCrypto.md5(fwBytes);
        clearCommands();
        conn.sendCommand(Proto.command(22, 0, null, null, Proto.dataUploadRequest(TYPE_WATCHFACE_FILE, md5, fwBytes.length)));
        resp = nextCommandOfType(22, 15000, "upload ack");
        cmd = Proto.parseCommand(resp);
        Proto.UploadAck ack = Proto.parseUploadAck(cmd.dataUpload);
        progress.log("Upload reply: subtype=" + cmd.subtype + " errno=" + (ack != null ? ack.errno : "n/a")
                + " resume=" + (ack != null ? ack.resumePosition : "n/a")
                + " chunk=" + (ack != null && ack.hasChunkSize ? ack.chunkSize : "n/a")
                + " raw=" + hexSnippet(resp));
        if (ack == null) throw new Exception("Unexpected upload reply (no ack in type-22 packet)");
        if (ack.errno != 0) throw new Exception("Upload rejected (errno=" + ack.errno + ")");
        int chunkSize = ack.hasChunkSize ? (int) ack.chunkSize : 2048;
        long resume = ack.resumePosition;
        progress.log("Upload chunk=" + chunkSize + " resume=" + resume);

        // 8. chunked upload: [00 type md5 size(fileLen) file[resume..]]+crc32, split with 4-byte part header.
        // Mirrors Gadgetbridge doUpload(): header keeps the FULL size, data starts at resumePosition.
        int resumeOff = (int) Math.min(Math.max(resume, 0), fwBytes.length);
        if (resumeOff > 0) progress.log("Resuming upload at byte " + resumeOff);
        byte[] payload = buildUploadPayload(fwBytes, md5, resumeOff);
        int partSize = chunkSize - 4;
        if (partSize <= 0) partSize = 2044;
        int totalParts = (int) Math.ceil(payload.length / (float) partSize);
        java.util.List<byte[]> parts = new java.util.ArrayList<>(totalParts);
        for (int i = 0; i < totalParts; i++) {
            int s = i * partSize;
            int e = Math.min((i + 1) * partSize, payload.length);
            byte[] chunk = new byte[4 + (e - s)];
            Proto.writeU16LE(chunk, 0, totalParts);
            Proto.writeU16LE(chunk, 2, i + 1);
            System.arraycopy(payload, s, chunk, 4, e - s);
            parts.add(chunk);
        }
        final int[] lastLogged = {0};
        conn.sendDataChunks(parts, (done, total) -> {
            int pct = Math.round(100f * done / total);
            progress.progress(pct);
            if (done - lastLogged[0] >= 25 || done == total) {
                lastLogged[0] = done;
                progress.log("Upload " + done + "/" + total + " (" + pct + "%)");
            }
        });
        progress.progress(100);
        progress.log("Upload complete");

        // 9. activate the face
        Thread.sleep(1500);
        progress.log("Activating watchface…");
        setActive(face.id);
        Thread.sleep(1000);
        progress.log("Done. If the face does not appear, select it manually on the watch.");
    }

    /** Queries the installed faces (type 4 subtype 0). Requires authentication. */
    public java.util.List<Proto.FaceInfo> faceList() throws Exception {
        clearCommands();
        conn.sendCommand(Proto.command(4, 0, null, null, null));
        long deadline = System.currentTimeMillis() + 15000;
        while (true) {
            long wait = deadline - System.currentTimeMillis();
            if (wait <= 0) throw new Exception("Timeout waiting for face list");
            byte[] resp = nextCommandOfType(4, wait, "face list");
            Proto.Command cmd = Proto.parseCommand(resp);
            java.util.List<Proto.FaceInfo> list = Proto.parseFaceList(cmd.watchface);
            if (!list.isEmpty() || cmd.subtype == 0) {
                if (!list.isEmpty()) return list;
                // Empty list reply: watch genuinely has no deletable faces listed; retry briefly
                // in case the reply was an ack to something else.
                Thread.sleep(500);
            }
        }
    }

    /** Sets a face active by id (type 4 subtype 1). */
    public void setActive(String id) throws Exception {
        conn.sendCommand(Proto.command(4, 1, null, Proto.watchfaceId(id), null));
        Thread.sleep(1000);
    }

    /** Deletes a user face by id (type 4 subtype 2), then returns the refreshed list. */
    public java.util.List<Proto.FaceInfo> deleteFace(String id) throws Exception {
        conn.sendCommand(Proto.command(4, 2, null, Proto.watchfaceId(id), null));
        Thread.sleep(1500);
        try {
            return faceList();
        } catch (Exception e) {
            return new java.util.ArrayList<>();
        }
    }

    private static byte[] buildUploadPayload(byte[] fw, byte[] md5, int resumeOff) {
        ByteBuffer b1 = ByteBuffer.allocate(2 + 16 + 4 + (fw.length - resumeOff)).order(ByteOrder.LITTLE_ENDIAN);
        b1.put((byte) 0);
        b1.put((byte) TYPE_WATCHFACE_FILE);
        b1.put(md5);
        b1.putInt(fw.length);
        b1.put(fw, resumeOff, fw.length - resumeOff);
        byte[] inner = b1.array();
        ByteBuffer b2 = ByteBuffer.allocate(inner.length + 4).order(ByteOrder.LITTLE_ENDIAN);
        b2.put(inner);
        b2.putInt((int) XiaomiCrypto.crc32(inner));
        return b2.array();
    }

    private static byte[] concat(byte[] a, byte[] b) {
        byte[] o = new byte[a.length + b.length];
        System.arraycopy(a, 0, o, 0, a.length);
        System.arraycopy(b, 0, o, a.length, b.length);
        return o;
    }
}
