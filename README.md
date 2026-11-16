# Online orders pipeline on LocalStack (SNS + SQS)

## 1. What it does

A tiny online-shop order pipeline running fully on your laptop with [LocalStack](https://docs.localstack.cloud) (free Hobby plan, only SNS and SQS).
A producer publishes orders (`order_id`, `customer`, `amount`) to an SNS topic. The topic fans them out to an SQS queue, and a consumer long-polls the queue, processes each order and deletes it.
Orders with a negative amount fail. They are not deleted, so after 3 receives SQS moves them to a dead-letter queue.

```
 producer.py ──publish──▶ SNS: orders-topic ──subscription──▶ SQS: orders-queue ──long poll──▶ consumer.py
                                                              (VisibilityTimeout 5s)            │ ok   → delete
                                                                       │                        │ fail → not deleted,
                                                                       │ after 3 receives       │        retried in 5s
                                                                       ▼
                                                              SQS: orders-dlq
```

| File | Purpose |
|------|---------|
| `src/setup.py` | creates topic, queue, DLQ (RedrivePolicy `maxReceiveCount=3`) and subscription; safe to re-run |
| `src/producer.py` | publishes N orders (default 5); `--bad` adds one order with a negative amount |
| `src/consumer.py` | long-polls `orders-queue` (`WaitTimeSeconds=20`), deletes on success, leaves failed orders |
| `src/teardown.py` | deletes topic, subscription and both queues |

## 2. Prerequisites

- macOS with **Docker Desktop** running
- **Python 3** (tested with 3.15)
- **AWS CLI v2**: `brew install awscli` (tested with 2.39)
- A **LocalStack account** (free Hobby plan, non-commercial) and your **auth token**: <https://app.localstack.cloud> → *Auth Tokens* (starts with `ls-`). Since March 2026 the emulator does not start without it.

## 3. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Start LocalStack

First put your token in `.env.localstack` (see [Configure](#5-configure)), then:

```bash
docker compose up -d
```
```
 Container localstack-main  Started
```

Health check (wait ~10 s after the start):

```bash
docker ps --format '{{.Names}}  {{.Image}}  {{.Status}}'
curl -s http://localhost:4566/_localstack/health | python3 -m json.tool | grep -E '"(sqs|sns|edition|version)"|persistence'
curl -s http://localhost:4566/_localstack/info
```
```
localstack-main  localstack/localstack:2026.10.1  Up 11 seconds (healthy)
        "persistence": "disabled"
        "sns": "available",
        "sqs": "available",
    "edition": "pro",
    "version": "2026.10.1"
{"version": "2026.10.1:3725556f", "edition": "pro", "is_license_activated": true, ...}
```

`is_license_activated: true` means the token worked. `"edition": "pro"` is the image edition and also appears on the Hobby plan. Services show `available` until first used, then `running`.

Stop LocalStack with `docker compose down`.

**Alternative: `lstk`** (LocalStack's CLI). Install with `brew install localstack/tap/lstk`. `lstk` starts the emulator (browser login the first time), `lstk status` shows it, `lstk stop` stops it, and AWS commands run as `lstk aws sqs list-queues`.
**Use only one method at a time.** Both bind port 4566 (lstk names its container `localstack-aws`). Check with `docker ps` and stop the other one first.

## 5. Configure

**Token** (never put it in code, `docker-compose.yml` or git; `.env.localstack` is in `.gitignore`):

```bash
cp .env.localstack.example .env.localstack
# edit .env.localstack:  LOCALSTACK_AUTH_TOKEN=ls-...your token...
```

**AWS settings** for the scripts and the AWS CLI (run in every new terminal):

```bash
export AWS_ENDPOINT_URL=http://localhost.localstack.cloud:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
```

These are also the defaults in the Python scripts. If `localhost.localstack.cloud` does not resolve (e.g. offline or DNS-rebind protection), the scripts fall back to `http://localhost:4566`. LocalStack's account id is always `000000000000`, so queue URLs look like `http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/<name>`.

## 6. Usage

Activate the venv, export the variables from section 5, and set two shortcuts:

```bash
Q=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-queue
DLQ=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-dlq
```

**1. Create** topic, queues and subscription (re-run after every LocalStack restart):

```bash
python src/setup.py
```
```
Endpoint:     http://localhost.localstack.cloud:4566
Topic:        arn:aws:sns:us-east-1:000000000000:orders-topic
Queue:        http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-queue
DLQ:          http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-dlq
Subscription: arn:aws:sns:us-east-1:000000000000:orders-topic:8be31a5c-a0f3-4c74-912c-545a0e6e4b72
```

**2. Publish** 3 orders (customers, amounts and IDs are random):

```bash
python src/producer.py 3
```
```
published {'order_id': 1, 'customer': 'bogdan', 'amount': 420.19} -> 2a3285d0-4857-4e71-8b97-8c59a52119c8
published {'order_id': 2, 'customer': 'carmen', 'amount': 447.56} -> 858c2f10-30a3-4c1f-a04b-346854ef0be5
published {'order_id': 3, 'customer': 'bogdan', 'amount': 81.12} -> 298653aa-2b4e-4915-aa3d-93e8ed6598a8
```

**3. Check the queue** (messages arrived through SNS):

```bash
aws sqs get-queue-attributes --queue-url $Q --attribute-names ApproximateNumberOfMessages
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "3"
    }
}
```

LocalStack-only inspection endpoint. It shows messages without receiving them, so it does not touch visibility or receive counts:

```bash
curl -s -H "Accept: application/json" "http://localhost.localstack.cloud:4566/_aws/sqs/messages?QueueUrl=$Q" | python3 -m json.tool | grep '"Body"'
```
```
                    "Body": "{\"order_id\": 1, \"customer\": \"bogdan\", \"amount\": 420.19}",
                    "Body": "{\"order_id\": 2, \"customer\": \"carmen\", \"amount\": 447.56}",
                    "Body": "{\"order_id\": 3, \"customer\": \"bogdan\", \"amount\": 81.12}",
```

**4. Consume** (stop with **Ctrl+C**):

```bash
python src/consumer.py
```
```
listening on http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-queue (Ctrl+C to stop)
processed order 1: bogdan paid 420.19
processed order 2: carmen paid 447.56
processed order 3: bogdan paid 81.12
^C stopped
```

```bash
aws sqs get-queue-attributes --queue-url $Q --attribute-names ApproximateNumberOfMessages
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "0"
    }
}
```

**5. Bad order → DLQ.** Publish 2 good orders + 1 bad one, then run the consumer for ~25 s and press Ctrl+C:

```bash
python src/producer.py 2 --bad
python src/consumer.py
```
```
published {'order_id': 1, 'customer': 'carmen', 'amount': 442.23} -> 9a1f5ce6-8710-456c-8f0a-f09b9d902d19
published {'order_id': 2, 'customer': 'ana', 'amount': 498.58} -> b2d04295-f930-4275-96d0-80252a57aaf5
published {'order_id': 3, 'customer': 'mallory', 'amount': -42.0} -> 118a5bda-91f9-46a7-9301-b0cb0a7a08dd
listening on http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-queue (Ctrl+C to stop)
processed order 2: ana paid 498.58
FAILED (receive #1): invalid amount -42.0 -> body={"order_id": 3, "customer": "mallory", "amount": -42.0}
processed order 1: carmen paid 442.23
FAILED (receive #2): invalid amount -42.0 -> body={"order_id": 3, "customer": "mallory", "amount": -42.0}
FAILED (receive #3): invalid amount -42.0 -> body={"order_id": 3, "customer": "mallory", "amount": -42.0}
^C stopped
```

The failed order reappears every 5 s (VisibilityTimeout). On the 4th receive SQS moves it to the DLQ instead of delivering it:

```bash
aws sqs get-queue-attributes --queue-url $DLQ --attribute-names ApproximateNumberOfMessages
aws sqs receive-message --queue-url $DLQ --visibility-timeout 0 --query 'Messages[].Body'
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "1"
    }
}
[
    "{\"order_id\": 3, \"customer\": \"mallory\", \"amount\": -42.0}"
]
```

**6. Purge** the DLQ (deletes all its messages; no output on success):

```bash
aws sqs purge-queue --queue-url $DLQ
aws sqs get-queue-attributes --queue-url $DLQ --attribute-names ApproximateNumberOfMessages
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "0"
    }
}
```

**7. Delete everything:**

```bash
python src/teardown.py
```
```
deleted topic arn:aws:sns:us-east-1:000000000000:orders-topic
deleted queue http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-queue
deleted queue http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/orders-dlq
```

## 7. Manual SQS walkthrough (AWS CLI)

Pure AWS CLI with an explicit endpoint, on separate `demo-queue` / `demo-dlq` queues. Credentials and region come from section 5.

```bash
EP=http://localhost.localstack.cloud:4566
```

**Create** a DLQ and a queue that sends messages there after 3 receives:

```bash
aws --endpoint-url $EP sqs create-queue --queue-name demo-dlq
aws --endpoint-url $EP sqs create-queue --queue-name demo-queue \
  --attributes '{"VisibilityTimeout":"5","RedrivePolicy":"{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:demo-dlq\",\"maxReceiveCount\":\"3\"}"}'
```
```json
{
    "QueueUrl": "http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/demo-dlq"
}
{
    "QueueUrl": "http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/demo-queue"
}
```

**Get the queue URL:**

```bash
aws --endpoint-url $EP sqs get-queue-url --queue-name demo-queue
DQ=$(aws --endpoint-url $EP sqs get-queue-url --queue-name demo-queue --query QueueUrl --output text)
DDLQ=$(aws --endpoint-url $EP sqs get-queue-url --queue-name demo-dlq --query QueueUrl --output text)
```
```json
{
    "QueueUrl": "http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/demo-queue"
}
```

**Send 3 messages:**

```bash
aws --endpoint-url $EP sqs send-message --queue-url $DQ --message-body '{"order_id": 1, "customer": "ana", "amount": 10.5}'
aws --endpoint-url $EP sqs send-message --queue-url $DQ --message-body '{"order_id": 2, "customer": "ana", "amount": 10.5}'
aws --endpoint-url $EP sqs send-message --queue-url $DQ --message-body '{"order_id": 3, "customer": "ana", "amount": 10.5}'
```
```json
{
    "MD5OfMessageBody": "13264bf80d38f495be3fec203adb3bae",
    "MessageId": "1f923206-e1ab-4ad9-a332-ab1aaac69ef6"
}
...  (one block per message)
```

**Count:**

```bash
aws --endpoint-url $EP sqs get-queue-attributes --queue-url $DQ --attribute-names ApproximateNumberOfMessages
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "3"
    }
}
```

**Peek.** SQS has no "list messages" call. Receiving with visibility timeout 0 shows messages without hiding them, but it still counts as a receive towards `maxReceiveCount`:

```bash
aws --endpoint-url $EP sqs receive-message --queue-url $DQ --max-number-of-messages 10 --visibility-timeout 0 --query 'Messages[].Body'
```
```json
[
    "{\"order_id\": 1, \"customer\": \"ana\", \"amount\": 10.5}",
    "{\"order_id\": 2, \"customer\": \"ana\", \"amount\": 10.5}",
    "{\"order_id\": 3, \"customer\": \"ana\", \"amount\": 10.5}"
]
```

**Consume one message.** Receive it, keep its receipt handle, then delete it (`delete-message` prints nothing on success):

```bash
RH=$(aws --endpoint-url $EP sqs receive-message --queue-url $DQ --query 'Messages[0].ReceiptHandle' --output text)
aws --endpoint-url $EP sqs delete-message --queue-url $DQ --receipt-handle "$RH"
aws --endpoint-url $EP sqs get-queue-attributes --queue-url $DQ --attribute-names ApproximateNumberOfMessages
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "2"
    }
}
```

**Purge** the remaining messages so the next demo is isolated (no output on success; AWS allows one purge per queue every 60 s):

```bash
aws --endpoint-url $EP sqs purge-queue --queue-url $DQ
aws --endpoint-url $EP sqs get-queue-attributes --queue-url $DQ --attribute-names ApproximateNumberOfMessages
```
```json
{
    "Attributes": {
        "ApproximateNumberOfMessages": "0"
    }
}
```

**Invalid message → DLQ.** Send `nu-e-json`, then act like a broken consumer: receive it without deleting. Each receive long-polls up to 10 s, waiting for the 5 s visibility timeout to expire. The 4th receive returns nothing because SQS moved the message to the DLQ:

```bash
aws --endpoint-url $EP sqs send-message --queue-url $DQ --message-body nu-e-json
for i in 1 2 3 4; do
  aws --endpoint-url $EP sqs receive-message --queue-url $DQ --wait-time-seconds 10 \
    --attribute-names ApproximateReceiveCount \
    --query 'Messages[0].[Body,Attributes.ApproximateReceiveCount]' --output text
done
aws --endpoint-url $EP sqs get-queue-attributes --queue-url $DDLQ --attribute-names ApproximateNumberOfMessages
aws --endpoint-url $EP sqs receive-message --queue-url $DDLQ --visibility-timeout 0 --query 'Messages[].Body'
```
```
{
    "MD5OfMessageBody": "5597dc1e5a446589b319a33a82a21cf1",
    "MessageId": "a1e65f6d-8c93-41fb-ac3a-47bd83bc52d4"
}
nu-e-json	1
nu-e-json	2
nu-e-json	3
None
{
    "Attributes": {
        "ApproximateNumberOfMessages": "1"
    }
}
[
    "nu-e-json"
]
```

**Delete** both queues (no output on success; the empty `list-queues` also prints nothing):

```bash
aws --endpoint-url $EP sqs delete-queue --queue-url $DQ
aws --endpoint-url $EP sqs delete-queue --queue-url $DDLQ
aws --endpoint-url $EP sqs list-queues
```

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Cannot connect to the Docker daemon at unix:///Users/<you>/.docker/run/docker.sock. Is the docker daemon running?` | Start Docker Desktop (`open -a Docker`), wait until `docker info` works. |
| Container exits right away (`docker ps -a` shows `Exited (55)`). `docker logs localstack-main` shows `License activation failed! 🔑❌ Reason: No credentials were found in the environment...` | Token missing: create `.env.localstack` with `LOCALSTACK_AUTH_TOKEN=ls-...` (section 5), then `docker compose up -d` again. |
| Same, but `Reason: The credentials defined in your environment are invalid.` | Token wrong or revoked: copy it again from app.localstack.cloud → Auth Tokens, no quotes or spaces. |
| `Bind for 127.0.0.1:4566 failed: port is already allocated` | Another LocalStack (e.g. started with `lstk`) is running. Check `docker ps`, then `lstk stop` or `docker stop <container>`. |
| `Sorry, the rds service is not included within your LocalStack license, but is available in an upgraded license.` | The Hobby plan covers only some services. This project uses only SNS and SQS, which are included. |
| `topic orders-topic not found - run: python src/setup.py` / `queue orders-queue not found ...` / `list-queues` prints nothing after a restart | Hobby has **no persistence**: every LocalStack restart wipes all resources. Run `python src/setup.py` again. |
| `Could not connect to the endpoint URL` | LocalStack is not running or still starting: check the health URL from section 4. |
