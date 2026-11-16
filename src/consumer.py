"""Long-poll orders-queue, process each order, delete it on success. Stop with Ctrl+C."""
import json
import sys

from setup import QUEUE, aws

sqs = aws("sqs")
try:
    queue_url = sqs.get_queue_url(QueueName=QUEUE)["QueueUrl"]
except sqs.exceptions.QueueDoesNotExist:
    sys.exit(f"queue {QUEUE} not found - run: python src/setup.py")
print(f"listening on {queue_url} (Ctrl+C to stop)")

try:
    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            AttributeNames=["ApproximateReceiveCount"],
        )
        for msg in resp.get("Messages", []):
            receives = msg["Attributes"]["ApproximateReceiveCount"]
            try:
                order = json.loads(msg["Body"])
                if order["amount"] < 0:
                    raise ValueError(f"invalid amount {order['amount']}")
                print(f"processed order {order['order_id']}: {order['customer']} paid {order['amount']}")
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            except Exception as e:
                # Not deleted: it reappears after the visibility timeout, then goes to the DLQ.
                print(f"FAILED (receive #{receives}): {e} -> body={msg['Body']}")
except KeyboardInterrupt:
    print("stopped")
