package com.example.glucosewatch6;

import android.content.Context;
import org.json.JSONObject;

final class CloudConfig {
    static final class Connection {
        final String endpoint,token;
        Connection(String endpoint,String token) { this.endpoint=endpoint;this.token=token; }
    }
    static volatile Connection current=new Connection("https://fixture.invalid","fixture-token");
    static Connection connection(Context context) { return current; }
    static JSONObject cacheDashboard(Context context,JSONObject result,Connection credentials) { return result; }
}
