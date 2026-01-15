from functools import lru_cache

import boto3


@lru_cache
def get_s3_client():
    """Get cached S3 client singleton."""
    return boto3.client("s3")


def delete_s3_prefix(bucket: str, prefix: str) -> int:
    """Delete all objects under a prefix."""
    s3 = get_s3_client()
    deleted_count = 0
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue

        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
        deleted_count += len(delete_keys)

    return deleted_count
