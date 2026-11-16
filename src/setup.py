"""Create the SNS topic, the SQS queue + DLQ and the subscription (safe to re-run)."""
import json
import os
import socket
from urllib.parse import urlparse

import boto3

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
TOPIC, QUEUE, DLQ = "orders-topic", "orders-queue", "orders-dlq"


def endpoint():
    url = os.environ.get("AWS_ENDPOINT_URL", "http://localhost.localstack.cloud:4566")
    try:
        socket.gethostbyname(urlparse(url).hostname)
    except socket.gaierror:
        url = "http://localhost:4566"  # DNS for localhost.localstack.cloud failed
    return url


def aws(service):
    return boto3.client(
        service,
        endpoint_url=endpoint(),
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


def queue_arn(sqs, url):
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])
    return attrs["Attributes"]["QueueArn"]


def main():
    sqs, sns = aws("sqs"), aws("sns")

    dlq_url = sqs.create_queue(QueueName=DLQ)["QueueUrl"]
    redrive = {"deadLetterTargetArn": queue_arn(sqs, dlq_url), "maxReceiveCount": "3"}
    queue_url = sqs.create_queue(
        QueueName=QUEUE,
        Attributes={"VisibilityTimeout": "5", "RedrivePolicy": json.dumps(redrive)},
    )["QueueUrl"]

    topic_arn = sns.create_topic(Name=TOPIC)["TopicArn"]
    sub_arn = sns.subscribe(
        TopicArn=topic_arn,
        Protocol="sqs",
        Endpoint=queue_arn(sqs, queue_url),
        Attributes={"RawMessageDelivery": "true"},  # deliver the order JSON as-is
    )["SubscriptionArn"]

    print(f"Endpoint:     {endpoint()}")
    print(f"Topic:        {topic_arn}")
    print(f"Queue:        {queue_url}")
    print(f"DLQ:          {dlq_url}")
    print(f"Subscription: {sub_arn}")


if __name__ == "__main__":
    main()
