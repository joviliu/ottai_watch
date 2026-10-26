import com.android.apksig.ApkSigner;
import java.io.File;
import java.nio.file.*;
import java.security.*;
import java.security.cert.*;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.*;

public class SignApk {
    public static void main(String[] args) throws Exception {
        String pem = new String(Files.readAllBytes(Paths.get(args[0])), java.nio.charset.StandardCharsets.US_ASCII);
        byte[] encoded = Base64.getMimeDecoder().decode(pem.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", ""));
        PrivateKey key = KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(encoded));
        X509Certificate cert;
        try (java.io.InputStream input = Files.newInputStream(Paths.get(args[1]))) {
            cert = (X509Certificate)CertificateFactory.getInstance("X.509").generateCertificate(input);
        }
        ApkSigner.SignerConfig signer = new ApkSigner.SignerConfig.Builder("personal", key, Collections.singletonList(cert)).build();
        new ApkSigner.Builder(Collections.singletonList(signer)).setInputApk(new File(args[2])).setOutputApk(new File(args[3]))
            .setMinSdkVersion(26).setV1SigningEnabled(true).setV2SigningEnabled(true).setV3SigningEnabled(true).build().sign();
    }
}
