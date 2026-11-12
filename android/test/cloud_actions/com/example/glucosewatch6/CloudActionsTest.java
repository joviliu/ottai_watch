package com.example.glucosewatch6;

import android.content.Context;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.cert.Certificate;
import java.util.*;
import java.util.concurrent.*;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

/** Runs the real foreground transport against an in-memory HTTPS connection, without a model call. */
public final class CloudActionsTest {
    private static final Context CONTEXT=new Context();
    private static final List<Connection> OPENED=Collections.synchronizedList(new ArrayList<Connection>());
    private static CountDownLatch blocked,release;
    private static final class Result implements CloudActions.Callback {
        final CountDownLatch done=new CountDownLatch(1);String error;
        @Override public void done(JSONObject result,int code,String error) { this.error=error;done.countDown(); }
        void await() throws Exception { check(done.await(5,TimeUnit.SECONDS),"request completed"); }
    }
    private static final class Connection extends HttpsURLConnection {
        final ByteArrayOutputStream bytes=new ByteArrayOutputStream();boolean outputClosed;
        Connection(URL url) { super(url); }
        @Override public OutputStream getOutputStream() { return new FilterOutputStream(bytes) { @Override public void close() throws IOException { outputClosed=true;super.close(); } }; }
        @Override public int getResponseCode() throws IOException {
            if(url.getPath().equals("/blocking"))try { blocked.countDown();if(!release.await(5,TimeUnit.SECONDS))throw new IOException(); }catch(InterruptedException error) { throw new IOException(error); }
            return 200;
        }
        @Override public InputStream getInputStream() { return new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)); }
        int length() { return fixedContentLength; }
        @Override public void disconnect() { }
        @Override public boolean usingProxy() { return false; }
        @Override public void connect() { }
        @Override public String getCipherSuite() { return "fixture"; }
        @Override public Certificate[] getLocalCertificates() { return null; }
        @Override public Certificate[] getServerCertificates() { return null; }
    }
    public static void main(String[] args) throws Exception {
        URL.setURLStreamHandlerFactory(protocol->"https".equals(protocol)?new URLStreamHandler() {
            @Override protected URLConnection openConnection(URL url) { Connection connection=new Connection(url);OPENED.add(connection);return connection; }
        }:null);
        try {
            Result blank=post("/api/v1/analysis",null);blank.await();Connection empty=OPENED.get(0);
            check(blank.error==null&&empty.getRequestMethod().equals("POST"),"bodyless analysis succeeds");
            check(empty.length()==0&&empty.bytes.size()==0&&empty.outputClosed,"null remains a closed zero-byte POST");
            check(empty.getRequestProperty("Content-Type")==null,"blank POST gains no JSON content type");

            blockWorkers();
            String json="{\"userContext\":\"晚饭后为什么升高？\\n含\\\"引号\\\"与🙂\"}";
            JSONObject body=new JSONObject(json);Result text=post("/api/v1/analysis",body);body.replaceForTest("{\"userContext\":\"later draft\"}");
            release.countDown();text.await();Connection sent=OPENED.get(OPENED.size()-1);byte[] expected=json.getBytes(StandardCharsets.UTF_8);
            check(text.error==null&&Arrays.equals(expected,sent.bytes.toByteArray()),"queued JSON captures original UTF-8 bytes");
            check(sent.length()==expected.length&&sent.outputClosed,"JSON fixed length matches actual bytes");
            check("application/json".equals(sent.getRequestProperty("Content-Type")),"context uses JSON content type");
            check("Bearer fixture-token".equals(sent.getRequestProperty("Authorization")),"authorization stays in HTTP header");

            blockWorkers();int count=OPENED.size();Result changed=post("/api/v1/analysis",new JSONObject(json));
            CloudConfig.current=new CloudConfig.Connection("https://other.invalid","different-token");release.countDown();changed.await();
            check(changed.error!=null&&OPENED.size()==count,"queued private context is not sent after connection changes");
            System.out.println("CloudActionsTest passed (zero-byte, JSON UTF-8, immutable snapshot, connection binding)");
        } finally {
            if(release!=null)release.countDown();
            for(String name:new String[]{"WORKER","CLOCK"}) { java.lang.reflect.Field field=CloudActions.class.getDeclaredField(name);field.setAccessible(true);((ExecutorService)field.get(null)).shutdownNow(); }
        }
    }
    private static Result post(String path,JSONObject body) { Result result=new Result();CloudActions.request(CONTEXT,"POST",path,body,result);return result; }
    private static void blockWorkers() throws Exception {
        blocked=new CountDownLatch(2);release=new CountDownLatch(1);post("/blocking",null);post("/blocking",null);check(blocked.await(5,TimeUnit.SECONDS),"workers blocked before queue test");
    }
    private static void check(boolean okay,String message) { if(!okay)throw new AssertionError(message); }
}
