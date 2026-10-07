# Java SDK Code Samples

Code examples for the Snowpipe Streaming Java SDK (High-Performance Architecture).

---

## Maven Dependency

```xml
<dependency>
    <groupId>com.snowflake</groupId>
    <artifactId>snowpipe-streaming</artifactId>
    <version>1.1.0</version> <!-- Use latest from Maven Central -->
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.18.1</version>
</dependency>
```

---

## Minimal Example

```java
import com.snowflake.ingest.streaming.*;
import java.util.*;

// Profile JSON file (same format as Python):
// { "account": "...", "user": "...", "url": "...", "private_key": "..." }

StreamingIngestClient client = new StreamingIngestClient(
    "my_client",          // client_name
    "MY_DATABASE",        // db_name
    "MY_SCHEMA",          // schema_name
    "MY_TABLE-STREAMING", // pipe_name
    "profile.json"        // profile_json path
);

StreamingIngestChannel channel = client.openChannel("channel_1");

Map<String, Object> row = new HashMap<>();
row.put("col1", "hello");
row.put("col2", 42);
row.put("col3", Map.of("nested", "data"));  // Native Map for VARIANT

channel.insertRow(row, "offset_1");

channel.close();
client.close();
```

---

## Batch Insert

```java
List<Map<String, Object>> rows = new ArrayList<>();
for (int i = 0; i < 1000; i++) {
    Map<String, Object> row = new HashMap<>();
    row.put("id", i);
    row.put("name", "record_" + i);
    row.put("payload", Map.of("index", i, "batch", true));
    rows.add(row);
}

channel.insertRows(rows, "0", String.valueOf(rows.size() - 1));
```

---

## Self-Healing Pattern

```java
private static final int MAX_RECOVERY = 3;

public void streamWithRetry(Map<String, Object> row, String offsetToken) {
    for (int attempt = 0; attempt < MAX_RECOVERY; attempt++) {
        try {
            channel.insertRow(row, offsetToken);
            return;
        } catch (SFException e) {
            String msg = e.getMessage().toLowerCase();
            boolean recoverable = msg.contains("token has expired")
                || msg.contains("invalid state")
                || msg.contains("invalidchannel");
            if (recoverable && attempt < MAX_RECOVERY - 1) {
                recoverChannel();
                continue;
            }
            throw e;
        }
    }
}

private synchronized void recoverChannel() {
    try { channel.close(); } catch (Exception ignored) {}
    channel = client.openChannel(channelName);
}
```
