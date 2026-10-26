package com.example.redmiwatch6installer.xiaomi;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Bluetooth Classic (SPP) connection speaking Xiaomi V1 framing, upgrading to V2
 * when the watch reports a protocol version &gt;= 2.
 *
 * <p>Derived from Gadgetbridge XiaomiSppSupport / XiaomiSppProtocolV1+V2 (AGPLv3).
 */
public final class SppConnection {
    private static final String TAG = "SppConnection";
    public static final UUID SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");

    public interface Listener {
        void onCommand(byte[] plainProtobuf);
        void onLog(String msg);
        void onDisconnected();
    }

    private final BluetoothDevice device;
    private final BluetoothAdapter adapter;
    private final Listener listener;
    private BluetoothSocket socket;
    private InputStream in;
    private OutputStream out;
    private Thread reader;
    private volatile boolean closed;

    private final ByteArrayOutputStream rxBuf = new ByteArrayOutputStream();

    // V1 state
    private int frameSerial;
    private int encCounter;
    private XiaomiCrypto.SessionKeys keys;
    private volatile boolean encrypted;

    // V2 state
    private volatile boolean useV2;
    // Gadgetbridge's send window starts DATA at seq 0 (session config does not consume data seq space)
    private int v2Seq;
    private final BlockingQueue<Integer> v2Acks = new LinkedBlockingQueue<>();
    private final BlockingQueue<Integer> v2Nacks = new LinkedBlockingQueue<>();
    private final BlockingQueue<byte[]> v2SessionResp = new LinkedBlockingQueue<>();

    public SppConnection(BluetoothAdapter adapter, BluetoothDevice device, Listener listener) {
        this.adapter = adapter;
        this.device = device;
        this.listener = listener;
    }

    public void setKeys(XiaomiCrypto.SessionKeys keys) {
        this.keys = keys;
        this.encrypted = keys != null;
        if (keys != null) encCounter = 1; // Gadgetbridge starts encryptedIndex at 1 (0 = auth)
    }

    public boolean isV2() {
        return useV2;
    }

    public void connect() throws IOException {
        // Like Gadgetbridge's BtBRQueue: stop discovery, it breaks RFCOMM connects.
        try {
            if (adapter != null && adapter.isDiscovering()) {
                log("Cancelling Bluetooth discovery…");
                adapter.cancelDiscovery();
            }
        } catch (SecurityException e) {
            log("No permission to cancel discovery: " + e.getMessage());
        }
        // Refresh SDP records (async, best effort)
        try {
            device.fetchUuidsWithSdp();
        } catch (SecurityException ignored) {
        }

        IOException lastError = null;
        // 1. secure SDP socket (what Gadgetbridge uses)
        try {
            log("SPP connect (secure)…");
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID);
            socket.connect();
            opened();
            return;
        } catch (IOException | SecurityException e) {
            lastError = new IOException("secure: " + e.getMessage(), e);
            log("Secure SPP failed: " + e.getMessage());
            closeQuiet(socket);
            socket = null;
        }
        // 2. insecure SDP socket
        try {
            log("SPP connect (insecure)…");
            socket = device.createInsecureRfcommSocketToServiceRecord(SPP_UUID);
            socket.connect();
            opened();
            return;
        } catch (IOException | SecurityException e) {
            lastError = new IOException("insecure: " + e.getMessage(), e);
            log("Insecure SPP failed: " + e.getMessage());
            closeQuiet(socket);
            socket = null;
        }
        // 3. direct channels (reflection fallback, skips SDP).
        // bt_stack snoop showed the watch's SPP on scn 5; try it first, then the rest.
        int[] channels = {5, 1, 2, 3, 4, 6, 7, 8};
        for (int ch : channels) {
            try {
                log("SPP connect (channel " + ch + ")…");
                Method m = BluetoothDevice.class.getMethod("createRfcommSocket", int.class);
                socket = (BluetoothSocket) m.invoke(device, ch);
                socket.connect();
                opened();
                return;
            } catch (Exception e) {
                log("Channel-" + ch + " SPP failed: " + e.getMessage());
                closeQuiet(socket);
                socket = null;
            }
        }
        throw lastError != null ? lastError : new IOException("SPP connect failed (no method worked)");
    }

    private void opened() throws IOException {
        in = socket.getInputStream();
        out = socket.getOutputStream();
        closed = false;
        reader = new Thread(this::readLoop, "spp-reader");
        reader.setDaemon(true);
        reader.start();
        log("SPP socket connected");
    }

    private static void closeQuiet(BluetoothSocket s) {
        if (s == null) return;
        try {
            s.close();
        } catch (IOException ignored) {
        }
    }

    public void close() {
        closed = true;
        try {
            if (socket != null) socket.close();
        } catch (IOException ignored) {
        }
    }

    private synchronized void write(byte[] b) throws IOException {
        out.write(b);
        out.flush();
    }

    // ---------- sends ----------

    public void sendVersionRequest() throws IOException {
        if (useV2) throw new IllegalStateException("already on V2");
        write(SppPacketV1.versionRequest());
    }

    public void sendAuthCommand(byte[] protobuf) throws IOException {
        // Auth channel is always plaintext framing (V1 DATA_AUTH / V2 PLAINTEXT opcode),
        // like Gadgetbridge's Channel.Authentication - even step 3, which carries
        // encrypted content inside the protobuf itself.
        if (useV2) {
            sendV2(SppPacketV1.Channel.COMMAND, protobuf, true, true);
        } else {
            byte[] f = SppPacketV1.encode(SppPacketV1.Channel.COMMAND, SppPacketV1.DATA_AUTH,
                    SppPacketV1.OP_SEND, frameSerial++ & 0xff, false, protobuf, null, 0);
            write(f);
        }
    }

    public void sendCommand(byte[] protobuf) throws IOException {
        if (useV2) {
            sendV2(SppPacketV1.Channel.COMMAND, protobuf, true, false);
        } else {
            byte[] f = SppPacketV1.encode(SppPacketV1.Channel.COMMAND, SppPacketV1.DATA_ENCRYPTED,
                    SppPacketV1.OP_SEND, frameSerial++ & 0xff, false, protobuf, keys, encCounter++);
            write(f);
        }
    }

    public interface ChunkProgress {
        void onPart(int done, int total);
    }

    /**
     * Windowed (go-back-N) bulk send, like Gadgetbridge's V2 send window.
     * V1 keeps the old one-at-a-time paced send.
     */
    public void sendDataChunks(java.util.List<byte[]> chunks, ChunkProgress progress) throws IOException {
        if (!useV2) {
            int i = 0;
            for (byte[] c : chunks) {
                sendDataChunk(c);
                progress.onPart(++i, chunks.size());
            }
            return;
        }
        final int WINDOW = 16;
        java.util.List<byte[]> payloads = new java.util.ArrayList<>(chunks.size());
        for (byte[] c : chunks) {
            payloads.add(SppV2.dataPayload(SppPacketV1.Channel.DATA, c, null, true));
        }
        java.util.LinkedHashMap<Integer, byte[]> unacked = new java.util.LinkedHashMap<>();
        int base = v2Seq & 0xff;
        int sent = 0, acked = 0;
        v2Acks.clear();
        v2Nacks.clear();
        while (acked < chunks.size()) {
            while (sent < chunks.size() && unacked.size() < WINDOW) {
                int seq = (base + sent) & 0xff;
                byte[] frame = SppV2.frame(SppV2.TYPE_DATA, seq, payloads.get(sent));
                unacked.put(seq, frame);
                write(frame);
                sent++;
            }
            Integer ack = null;
            try {
                ack = v2Acks.poll(3000, TimeUnit.MILLISECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException("interrupted", e);
            }
            Integer nack = v2Nacks.poll();
            if (nack != null) {
                // Go-back-N: resend everything from the expected seq onward
                int expected = nack & 0xff;
                log("V2 nack, resend from seq=" + expected);
                boolean found = false;
                for (java.util.Map.Entry<Integer, byte[]> e : unacked.entrySet()) {
                    if ((e.getKey() & 0xff) == expected) found = true;
                    if (found) write(e.getValue());
                }
                if (!found) resendAll(unacked);
            } else if (ack != null) {
                // Cumulative ACK: release everything up to and including acked seq
                int a = ack & 0xff;
                java.util.Iterator<Integer> it = unacked.keySet().iterator();
                boolean found = false;
                while (it.hasNext()) {
                    int k = it.next();
                    it.remove();
                    acked++;
                    if (k == a) {
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    // stale/unknown ACK, resend outstanding to be safe
                    resendAll(unacked);
                } else {
                    progress.onPart(acked, chunks.size());
                }
            } else {
                log("V2 upload timeout, resending " + unacked.size() + " frames");
                resendAll(unacked);
            }
        }
        v2Seq = (base + chunks.size()) & 0xff;
    }

    private void resendAll(java.util.LinkedHashMap<Integer, byte[]> unacked) throws IOException {
        for (byte[] f : unacked.values()) write(f);
    }

    public void sendDataChunk(byte[] chunk) throws IOException {
        if (useV2) {
            // Stop-and-wait: slow but reliable (watch ACKs every frame, drops on overflow)
            sendV2(SppPacketV1.Channel.DATA, chunk, true, false);
        } else {
            byte[] f = SppPacketV1.encode(SppPacketV1.Channel.DATA, SppPacketV1.DATA_ENCRYPTED,
                    SppPacketV1.OP_SEND, frameSerial++ & 0xff, false, chunk, keys, 0);
            write(f);
            // V1 has no per-packet ACK on SPP; small pacing avoids overrunning the watch
            try {
                Thread.sleep(5);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private void sendV2(SppPacketV1.Channel channel, byte[] body, boolean waitAck, boolean plaintext) throws IOException {
        // Note: the frame checksum covers the payload only, so the same payload can be
        // re-framed with a different sequence number on resend (like Gadgetbridge).
        byte[] payload = SppV2.dataPayload(channel, body, keys, plaintext);
        int seq = v2Seq & 0xff;
        for (int attempt = 0; ; attempt++) {
            // drop stale signals from previous attempts
            while (v2Acks.remove(Integer.valueOf(seq))) { /* drain */ }
            v2Nacks.clear();
            write(SppV2.frame(SppV2.TYPE_DATA, seq, payload));
            if (!waitAck) {
                v2Seq = (seq + 1) & 0xff;
                return;
            }
            log("V2 send seq=" + seq + " (" + payload.length + "B, attempt " + (attempt + 1) + ")");
            long deadline = System.currentTimeMillis() + 8000;
            boolean nacked = false;
            while (System.currentTimeMillis() < deadline) {
                long wait = deadline - System.currentTimeMillis();
                try {
                    Integer ack = v2Acks.poll(wait, TimeUnit.MILLISECONDS);
                    if (ack != null && (ack & 0xff) == seq) {
                        log("V2 ack seq=" + seq);
                        v2Seq = (seq + 1) & 0xff;
                        return;
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("interrupted waiting for ACK", e);
                }
                Integer nack = v2Nacks.poll();
                if (nack != null) {
                    int expected = nack & 0xff;
                    log("V2 nack, watch expects seq=" + expected + " (we sent " + seq + ")");
                    seq = expected;
                    nacked = true;
                    break;
                }
            }
            if (nacked) {
                continue; // NACK-driven resend does not consume a timeout attempt
            }
            if (attempt >= 2) throw new IOException("No ACK for V2 packet seq=" + seq);
            log("V2 timeout seq=" + seq + ", resending");
        }
    }

    public void upgradeToV2AndStartSession() throws IOException {
        useV2 = true;
        v2Seq = 0; // DATA sequence space starts at 0, like Gadgetbridge's send window
        byte[] req = SppV2.sessionStartRequest(0);
        v2SessionResp.clear();
        write(req);
        log("V2 session request sent, waiting for response…");
        try {
            byte[] resp = v2SessionResp.poll(8000, TimeUnit.MILLISECONDS);
            if (resp == null) log("no V2 session response, continuing anyway");
            else log("V2 session established (resp " + resp.length + "B)");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("interrupted", e);
        }
    }

    // ---------- receive ----------

    private void readLoop() {
        byte[] tmp = new byte[8192];
        try {
            while (!closed) {
                int n = in.read(tmp);
                if (n < 0) break;
                synchronized (rxBuf) {
                    rxBuf.write(tmp, 0, n);
                    drain();
                }
            }
        } catch (IOException e) {
            if (!closed) log("socket read error: " + e.getMessage());
        } finally {
            if (!closed) {
                // Remote drop (not our close()): no more traffic possible on this socket.
                // The owner reconnects; this gap is when the vendor app would grab the watch.
                log("link dropped");
                try {
                    listener.onDisconnected();
                } catch (Exception ignored) {
                }
            }
        }
    }

    private void drain() {
        byte[] buf = rxBuf.toByteArray();
        int off = 0;
        while (off < buf.length) {
            int remain = buf.length - off;
            // detect framing by preamble
            if (!useV2 && remain >= 3 && buf[off] == (byte) 0xba && buf[off + 1] == (byte) 0xdc
                    && buf[off + 2] == (byte) 0xfe) {
                SppPacketV1.Decoded d = SppPacketV1.decodeOne(buf, off, remain);
                if (d == null) break; // incomplete
                off += d.totalLen;
                handleV1(d);
            } else if (useV2 && remain >= 2 && buf[off] == (byte) 0xa5 && buf[off + 1] == (byte) 0xa5) {
                SppV2.Decoded d = SppV2.decodeOne(buf, off, remain);
                if (d == null) {
                    // bad checksum or incomplete: if enough bytes for header, skip one byte
                    if (remain >= 8) {
                        int plen = (buf[off + 4] & 0xff) | ((buf[off + 5] & 0xff) << 8);
                        if (remain >= 8 + plen) off++; // corrupt, skip
                        else break; // incomplete
                    } else break;
                    continue;
                }
                off += d.totalLen;
                handleV2(d);
            } else {
                // pre-upgrade: only V1 expected; V2 frames can only appear after upgrade
                if (!useV2 && remain >= 2 && buf[off] == (byte) 0xa5 && buf[off + 1] == (byte) 0xa5) {
                    Log.w(TAG, "V2 preamble before upgrade, skipping byte");
                    off++;
                } else {
                    // unknown byte, skip
                    off++;
                }
                if (off < buf.length && (buf.length - off) < 11 && !useV2) break;
            }
        }
        // compact
        byte[] left = new byte[buf.length - off];
        System.arraycopy(buf, off, left, 0, left.length);
        rxBuf.reset();
        rxBuf.write(left, 0, left.length);
    }

    private void handleV1(SppPacketV1.Decoded d) {
        if (d.channel == SppPacketV1.Channel.VERSION) {
            int version = d.payload.length > 0 ? (d.payload[0] & 0xff) : 0;
            log("SPP version: " + version);
            listener.onCommand(new byte[]{(byte) 0xFE, (byte) version}); // sentinel for version
            return;
        }
        byte[] plain = d.payload;
        if (d.dataType == SppPacketV1.DATA_ENCRYPTED) {
            if (keys == null || !encrypted) {
                log("encrypted packet before auth, ignoring");
                return;
            }
            try {
                plain = XiaomiCrypto.decryptV1(keys.decKey, keys.decNonce, d.payload);
            } catch (Exception e) {
                log("decrypt failed: " + e.getMessage());
                return;
            }
        }
        if (d.channel == SppPacketV1.Channel.COMMAND) {
            listener.onCommand(plain);
        } else {
            Log.d(TAG, "V1 non-command channel " + d.channel + " len=" + plain.length);
        }
    }

    private void handleV2(SppV2.Decoded d) {
        try {
            if (d.type == SppV2.TYPE_ACK) {
                v2Acks.offer(d.seq);
            } else if (d.type == SppV2.TYPE_NACK) {
                v2Nacks.offer(d.seq);
                log("V2 NACK seq=" + d.seq);
            } else if (d.type == SppV2.TYPE_SESSION) {
                v2SessionResp.offer(d.payload);
            } else if (d.type == SppV2.TYPE_DATA) {
                // ACK immediately (Gadgetbridge ACKs the received sequence)
                write(SppV2.ack(d.seq));
                if (d.payload.length < 2) return;
                int raw = d.payload[0] & 0xf;
                int op = d.payload[1] & 0xff;
                byte[] body = new byte[d.payload.length - 2];
                System.arraycopy(d.payload, 2, body, 0, body.length);
                if (op == SppV2.OP_ENCRYPTED) {
                    if (keys == null) {
                        log("encrypted V2 packet before auth");
                        return;
                    }
                    try {
                        body = XiaomiCrypto.ctrCrypt(keys.decKey, body);
                    } catch (Exception e) {
                        log("V2 decrypt failed: " + e.getMessage());
                        return;
                    }
                }
                if (raw == SppV2.RAW_PROTOBUF) {
                    listener.onCommand(body);
                }
            }
        } catch (IOException e) {
            log("V2 handle error: " + e.getMessage());
        }
    }

    private void log(String m) {
        listener.onLog(m);
    }
}
