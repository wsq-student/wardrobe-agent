import base64
import io
import uuid
import boto3
from botocore.exceptions import ClientError
from PIL import Image, ImageOps, UnidentifiedImageError
from .core import settings

Image.MAX_IMAGE_PIXELS = 25_000_000


def client():
    s = settings()
    return boto3.client('s3', endpoint_url=s.s3_endpoint, aws_access_key_id=s.s3_access_key,
                        aws_secret_access_key=s.s3_secret_key, region_name='us-east-1')


def init_bucket():
    c = client()
    try:
        c.head_bucket(Bucket=settings().s3_bucket)
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('404', 'NoSuchBucket'):
            raise
        c.create_bucket(Bucket=settings().s3_bucket)


def save_image(user_id: int, data: bytes):
    if len(data) > 12 * 1024 * 1024:
        raise ValueError('图片不能超过 12 MB')
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((1600, 1600))
            output = io.BytesIO()
            im.save(output, format='JPEG', quality=90)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('请上传有效的 JPG、PNG 或 WebP 图片') from exc
    key = f'{user_id}/{uuid.uuid4()}.jpg'
    client().put_object(Bucket=settings().s3_bucket, Key=key, Body=output.getvalue(), ContentType='image/jpeg')
    return key


def read(key):
    return client().get_object(Bucket=settings().s3_bucket, Key=key)['Body'].read()


def delete(key):
    if key:
        client().delete_object(Bucket=settings().s3_bucket, Key=key)


def data_uri(key):
    return 'data:image/jpeg;base64,' + base64.b64encode(read(key)).decode()
