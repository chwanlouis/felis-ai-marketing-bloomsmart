import os


class EnvironmentHandler:
    def __init__(self) -> None:
        self.DYNAMODB_TABLE_PRODUCT = os.getenv("DYNAMODB_TABLE_PRODUCT", None)
        self.DYNAMODB_TABLE_USER = os.getenv("DYNAMODB_TABLE_USER", None)
        self.DYNAMODB_TABLE_SESSION = os.getenv("DYNAMODB_TABLE_SESSION", None)
        self.DYNAMODB_TABLE_ORDER = os.getenv("DYNAMODB_TABLE_ORDER", None)
        self.AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
        self.S3_BUCKET_NAME = os.environ.get(
            "S3_BUCKET_NAME",
            os.environ.get("AWS_S3_BUCKET_NAME"),
        )
        self.GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


environment_handler = EnvironmentHandler()
