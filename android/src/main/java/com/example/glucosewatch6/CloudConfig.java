package com.example.glucosewatch6;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class CloudConfig {
    static final String PREFS = "ottai_cloud";
    private static final String KEY = "ottai-cloud-device-token";
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences(PREFS, 0); }
    static String endpoint(Context c) { return prefs(c).getString("endpoint", ""); }
    static String token(Context c) throws Exception {
        String saved = prefs(c).getString("token", "");
        if (saved.isEmpty()) return "";
        String[] parts = saved.split(":");
        if (parts.length != 2) throw new IllegalStateException("凭据需要重新保存");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), java.nio.charset.StandardCharsets.UTF_8);
    }
    static boolean configured(Context c) { return !endpoint(c).isEmpty() && !prefs(c).getString("token", "").isEmpty(); }
    static void save(Context c, String endpoint, String token) throws Exception {
        String address = CloudPolicy.endpoint(endpoint);
        if (token.isEmpty()) token = token(c);
        if (!CloudPolicy.validToken(token)) throw new IllegalArgumentException("请填写至少 16 位的设备上传令牌");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        String encrypted = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":"
            + Base64.encodeToString(cipher.doFinal(token.getBytes(java.nio.charset.StandardCharsets.UTF_8)), Base64.NO_WRAP);
        if (!prefs(c).edit().putString("endpoint", address).putString("token", encrypted).commit())
            throw new IllegalStateException("设置保存失败");
    }
    private static SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias(KEY)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(KEY, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey)store.getKey(KEY, null);
    }
}
