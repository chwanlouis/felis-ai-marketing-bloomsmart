import boto3
import uuid
from fastapi import UploadFile
from tools.env_handler import environment_handler
from tools.logger import get_logger


logger = get_logger(__name__)
s3_client = boto3.client("s3")


def upload_photo_to_s3(file: UploadFile) -> str:
    """
    Upload an uploaded photo file to S3 and return its public URL.
    """
    if not file or not file.filename:
        return ""

    file_ext = file.filename.split(".")[-1]
    file_name = f"products/{uuid.uuid4()}.{file_ext}"
    try:
        s3_client.upload_fileobj(
            file.file,
            environment_handler.S3_BUCKET_NAME,
            file_name,
            ExtraArgs={"ContentType": file.content_type},
        )
        return f"https://{environment_handler.S3_BUCKET_NAME}.s3.{environment_handler.AWS_REGION}.amazonaws.com/{file_name}"
    except Exception as e:
        logger.exception("S3 upload failed")
        return ""
