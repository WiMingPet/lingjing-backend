"""
文件上传工具
"""
import uuid
from typing import Tuple
from fastapi import UploadFile
from app.services.oss_service import oss_service


async def upload_file_to_oss(
    file: UploadFile,
    sub_folder: str = "uploads"
) -> Tuple[str, str]:
    """
    上传文件到 OSS
    
    Args:
        file: 上传的文件对象
        sub_folder: OSS 子文件夹名称
    
    Returns:
        (file_url, file_id) 元组，file_url 是 OSS 公网地址，file_id 是文件名
    """
    # 读取文件内容
    content = await file.read()
    
    # 获取文件扩展名
    extension = file.filename.split(".")[-1].lower()
    
    # 生成唯一文件名（作为 file_id）
    file_id = f"{uuid.uuid4()}.{extension}"
    full_path = f"{sub_folder}/{file_id}"
    
    # 上传到 OSS
    headers = {
        'Content-Type': f'image/{extension}' if extension in ['jpg', 'jpeg', 'png', 'webp', 'gif'] else 'application/octet-stream',
        'x-oss-object-acl': 'public-read',
        'Content-Disposition': 'inline'
    }
    
    oss_service.bucket.put_object(full_path, content, headers=headers)
    
    # 生成公网 URL
    endpoint = oss_service.bucket.endpoint
    if endpoint.startswith('https://'):
        endpoint = endpoint[8:]
    if endpoint.startswith('http://'):
        endpoint = endpoint[7:]
    file_url = f"https://{oss_service.bucket.bucket_name}.{endpoint}/{full_path}"
    
    # 重置文件指针（以便后续可能再次读取）
    await file.seek(0)
    
    return file_url, file_id


# 保留原有函数名，方便调用
upload_file_helper = upload_file_to_oss