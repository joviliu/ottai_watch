package com.example.ottaiwatchfaceinstaller;
import com.example.redmiwatch6installer.xiaomi.WatchfaceParser;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public final class InstallGuardTest {
    private static void reject(Runnable action) {try{action.run();throw new AssertionError("must reject");}catch(IllegalArgumentException expected){}}
    public static void main(String[] args) throws Exception {
        if (!InstallGuard.mode("list") || !InstallGuard.mode("auth") || !InstallGuard.mode("install") || !InstallGuard.mode("replace")
                || InstallGuard.mode(null) || InstallGuard.mode("firmware")) throw new AssertionError("operation mode allowlist");
        reject(()->InstallGuard.credentials("invalid", "invalid"));
        reject(()->InstallGuard.credentials("00:00:00:00:00:00", "invalid"));
        reject(()->InstallGuard.face(true,"wrong",432,514));
        reject(()->InstallGuard.deletionTarget("wrong"));
        reject(()->InstallGuard.deletionTarget(null));
        if (!"8670260101".equals(InstallGuard.deletionTarget("8670260101"))) throw new AssertionError("only project deletion ID");
        reject(()->InstallGuard.face(true,"8670260101",212,520));
        byte[] data=new byte[256];data[0]=0x5a;data[1]=(byte)0xa5;
        System.arraycopy("8670260101".getBytes(StandardCharsets.US_ASCII),0,data,40,10);
        System.arraycopy("Ottai Minimal".getBytes(StandardCharsets.US_ASCII),0,data,104,13);
        ByteBuffer b=ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);b.putInt(32,160);b.putShort(164,(short)432);b.putShort(166,(short)514);
        WatchfaceParser face=WatchfaceParser.parse(data);
        InstallGuard.face(face.valid&&face.compatibleEnoughToInstall(),face.id,face.previewWidth,face.previewHeight);
        if(WatchfaceParser.parse(new byte[20]).valid)throw new AssertionError("short input");
        if(args.length==1) {
            face=WatchfaceParser.parse(Files.readAllBytes(Paths.get(args[0])));
            InstallGuard.face(face.valid&&face.compatibleEnoughToInstall(),face.id,face.previewWidth,face.previewHeight);
        }
        String safe=InstallGuard.safeError(new Exception("device 00:00:00:00:00:00 raw=abcd"));
        if(safe.contains("00:00")||safe.contains("raw="))throw new AssertionError("error redaction");
        if (InstallGuard.safeProgress("Auth step 1 (nonce 1234)") != null) throw new AssertionError("nonce progress rejected");
        if (InstallGuard.safeProgress("Skip interleaved cmd type=1 raw=1234") != null) throw new AssertionError("protocol progress rejected");
        if (!"Install reply: subtype=4 status=0".equals(InstallGuard.safeProgress("Install reply: subtype=4 status=0 raw=1234567890abcdef"))) throw new AssertionError("raw progress truncated");
        if (!"SPP version: 2".equals(InstallGuard.safeProgress("SPP version: 2"))) throw new AssertionError("version stage retained");
        if (!"Upload chunk=2048 resume=0".equals(InstallGuard.safeProgress("Upload chunk=2048 resume=0"))) throw new AssertionError("upload stage retained");
        if (InstallGuard.safeProgress("Install reply: nonce secret raw=1234") != null) throw new AssertionError("secret stage rejected");
        System.out.println("SPP installer input guard, parser, stage whitelist and error-redaction checks passed");
    }
}
