package org.json;

/** Transport fixtures supply serialized JSON; this host stub intentionally does not parse it. */
public final class JSONObject {
    private String json;
    public JSONObject(String json) { this.json=json; }
    public int optInt(String key) { return 0; }
    public void replaceForTest(String value) { json=value; }
    @Override public String toString() { return json; }
}
