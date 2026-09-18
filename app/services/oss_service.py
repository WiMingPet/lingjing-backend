"""
阿里云 OSS 服务
用于上传和下载文件
"""
import oss2
import uuid
from typing import Optional
from app.config import settings


class OSSService:
    """OSS 服务类"""
    
    def __init__(self):
        """初始化 OSS 客户端"""
        auth = oss2.Auth(
            settings.OSS_ACCESS_KEY_ID,
            settings.OSS_ACCESS_KEY_SECRET
        )
        self.bucket = oss2.Bucket(
            auth,
            settings.OSS_ENDPOINT,
            settings.OSS_BUCKET_NAME
        )
    
    def _get_content_type(self, file_extension: str) -> str:
        """根据文件扩展名获取 Content-Type"""
        content_type_map = {
            "mp4": "video/mp4",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
            "aac": "audio/aac",
        }
        return content_type_map.get(file_extension.lower(), "application/octet-stream")
    
    async def upload_file(
        self, 
        file_content: bytes, 
        file_extension: str,
        sub_folder: str = "uploads",
        bucket_name: str = None
    ) -> str:
        """
        上传文件到 OSS
        - bucket_name 为空：用默认 Bucket（公共读）
        - bucket_name 传入：用指定 Bucket（私有 Bucket）
        """
        filename = f"{sub_folder}/{uuid.uuid4()}.{file_extension}"
        content_type = self._get_content_type(file_extension)

        actual_bucket_name = bucket_name or settings.OSS_BUCKET_NAME

        if bucket_name and bucket_name != settings.OSS_BUCKET_NAME:
            # 私有 Bucket
            auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
            target_bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, actual_bucket_name)
            headers = {
                'Content-Type': content_type,
                'Content-Disposition': 'inline',
            }
        else:
            # 默认公共读 Bucket
            target_bucket = self.bucket
            headers = {
                'Content-Type': content_type,
                'x-oss-object-acl': 'public-read',
                'Content-Disposition': 'inline',
            }

        target_bucket.put_object(filename, file_content, headers=headers)

        url = f"https://{actual_bucket_name}.{settings.OSS_ENDPOINT}/{filename}"
        print(f"[OSS] 文件上传成功: {url}, Content-Type: {content_type}, Bucket: {actual_bucket_name}")
        return url
    
    async def upload_file_from_url(
        self,
        file_url: str,
        file_extension: str,
        sub_folder: str = "uploads",
        bucket_name: str = None
    ) -> str:
        """从网络 URL 下载文件并上传到 OSS"""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            response.raise_for_status()
            return await self.upload_file(
                response.content,
                file_extension,
                sub_folder,
                bucket_name=bucket_name,
            )
    
    def delete_file(self, file_url: str) -> bool:
        """删除 OSS 中的文件"""
        filename = file_url.split(f"{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT}/")[-1]
        try:
            self.bucket.delete_object(filename)
            return True
        except Exception:
            return False


oss_service = OSSService()