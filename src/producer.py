"""Publish N orders to the SNS topic. Usage: python src/producer.py [N] [--bad]"""
import argparse
import json
import random
import sys

from setup import TOPIC, aws

parser = argparse.ArgumentParser()
parser.add_argument("n", type=int, nargs="?", default=5, help="number of orders (default 5)")
parser.add_argument("--bad", action="store_true", help="also send one order with a negative amount")
args = parser.parse_args()

sns = aws("sns")
topics = [t["TopicArn"] for t in sns.list_topics()["Topics"] if t["TopicArn"].endswith(f":{TOPIC}")]
if not topics:
    sys.exit(f"topic {TOPIC} not found - run: python src/setup.py")
topic_arn = topics[0]

orders = [
    {"order_id": i, "customer": random.choice(["ana", "bogdan", "carmen", "dan"]),
     "amount": round(random.uniform(10, 500), 2)}
    for i in range(1, args.n + 1)
]
if args.bad:
    orders.append({"order_id": args.n + 1, "customer": "mallory", "amount": -42.0})

for order in orders:
    msg_id = sns.publish(TopicArn=topic_arn, Message=json.dumps(order))["MessageId"]
    print(f"published {order} -> {msg_id}")
