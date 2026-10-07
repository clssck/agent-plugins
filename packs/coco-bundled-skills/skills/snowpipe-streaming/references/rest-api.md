# REST API Code Samples

Code examples for the Snowpipe Streaming REST API (High-Performance Architecture) — for lightweight workloads, IoT devices, or edge deployments.

---

## Authentication (JWT)

Generate a JWT token for REST API access:

```python
import jwt
import time
from cryptography.hazmat.primitives import serialization

with open("keys/rsa_key.p8", "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

now = int(time.time())
payload = {
    "iss": f"{ACCOUNT}.{USER}.SHA256:{FINGERPRINT}",
    "sub": f"{ACCOUNT}.{USER}",
    "iat": now,
    "exp": now + 3600,
}
token = jwt.encode(payload, private_key, algorithm="RS256")
```

---

## Append Rows

```bash
curl -X POST \
  "https://<account>.snowflakecomputing.com/v1/streaming/channels/<channel>/rows" \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Content-Encoding: zstd" \
  -d '{
    "rows": [
      {"col1": "value1", "col2": 42},
      {"col1": "value2", "col2": 43}
    ],
    "offset_token": "100"
  }'
```

---

## Compression

REST API has a 4MB request limit on transfer size. Use ZSTD compression to fit more data:

```python
import zstandard
import json
import requests

data = json.dumps({"rows": rows}).encode()
compressor = zstandard.ZstdCompressor()
compressed = compressor.compress(data)

response = requests.post(
    f"https://{account}.snowflakecomputing.com/v1/streaming/channels/{channel}/rows",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Content-Encoding": "zstd",
    },
    data=compressed,
)
```

---

## Full Python REST Client Example

```python
import jwt
import time
import json
import requests
import zstandard
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.hashes import SHA256

class StreamingRESTClient:
    def __init__(self, account, user, private_key_path):
        self.account = account
        self.user = user
        self.base_url = f"https://{account}.snowflakecomputing.com"

        with open(private_key_path, "rb") as f:
            self.private_key = serialization.load_pem_private_key(f.read(), password=None)

        pub_bytes = self.private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        from hashlib import sha256
        import base64
        self.fingerprint = base64.b64encode(sha256(pub_bytes).digest()).decode()

        self.compressor = zstandard.ZstdCompressor()
        self._token = None
        self._token_exp = 0

    def _get_token(self):
        now = int(time.time())
        if self._token and now < self._token_exp - 60:
            return self._token

        payload = {
            "iss": f"{self.account}.{self.user}.SHA256:{self.fingerprint}",
            "sub": f"{self.account}.{self.user}",
            "iat": now,
            "exp": now + 3600,
        }
        self._token = jwt.encode(payload, self.private_key, algorithm="RS256")
        self._token_exp = now + 3600
        return self._token

    def append_rows(self, channel_name, rows, offset_token=None, compress=True):
        body = {"rows": rows}
        if offset_token:
            body["offset_token"] = offset_token

        data = json.dumps(body).encode()
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

        if compress:
            data = self.compressor.compress(data)
            headers["Content-Encoding"] = "zstd"

        return requests.post(
            f"{self.base_url}/v1/streaming/channels/{channel_name}/rows",
            headers=headers,
            data=data,
        )
```

Usage:

```python
client = StreamingRESTClient(
    account="myorg-myaccount",
    user="STREAMING_USER",
    private_key_path="keys/rsa_key.p8",
)

response = client.append_rows(
    channel_name="my_channel",
    rows=[{"col1": "val1", "col2": 1}, {"col1": "val2", "col2": 2}],
    offset_token="42",
)
print(response.status_code, response.json())
```
