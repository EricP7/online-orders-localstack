"""Delete the topic (and its subscriptions) and both queues."""
from setup import DLQ, QUEUE, TOPIC, aws

sns, sqs = aws("sns"), aws("sqs")

for topic in sns.list_topics()["Topics"]:
    if topic["TopicArn"].endswith(f":{TOPIC}"):
        for sub in sns.list_subscriptions_by_topic(TopicArn=topic["TopicArn"])["Subscriptions"]:
            sns.unsubscribe(SubscriptionArn=sub["SubscriptionArn"])
        sns.delete_topic(TopicArn=topic["TopicArn"])
        print(f"deleted topic {topic['TopicArn']}")

for name in (QUEUE, DLQ):
    try:
        url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    except sqs.exceptions.QueueDoesNotExist:
        print(f"queue {name} not found, skipping")
        continue
    sqs.delete_queue(QueueUrl=url)
    print(f"deleted queue {url}")
