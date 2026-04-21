"""
文件上传工具
"""
import uuid
import os
import io
from typing import Tuple
from fastapi import UploadFile
from app.services.oss_service import oss_service
from PIL import Image



async def convert_to_supported_format(file_content: bytes, original_filename: str) -> Tuple[bytes, str]:
    """
    将图片转换为 JPEG 格式（可灵 API 支持）
    返回: (转换后的内容, 新的文件名)
    """
    try:
        # 打开图片
        img = Image.open(io.BytesIO(file_content))
        
        # 转换 RGBA 为 RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 保存为 JPEG
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=90)
        output.seek(0)
        
        # 生成新文件名
        name, ext = os.path.splitext(original_filename)
        new_filename = f"{name}.jpg"
        
        return output.getvalue(), new_filename
    except Exception as e:
        print(f"图片转换失败: {e}")
        return file_content, original_filename


async def upload_file_helper(
    file: UploadFile,
    sub_folder: str = "uploads"
) -> Tuple[str, str]:
    """
    上传文件到 OSS，自动转换图片格式
    
    Args:
        file: 上传的文件对象
        sub_folder: OSS 子文件夹名称
    
    Returns:
        (file_url, file_id) 元组，file_url 是 OSS 公网地址，file_id 是文件名
    """
    # 读取文件内容
    content = await file.read()
    filename = file.filename or "unknown"
    
    # 如果是图片文件，自动转换为 JPEG
    if file.content_type and file.content_type.startswith('image/'):
        content, filename = await convert_to_supported_format(content, filename)
    
    # 获取文件扩展名
    extension = filename.split(".")[-1].lower()
    
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
    file_url = f"https://media.lingjing-media.com/{full_path}"
    
    # 重置文件指针（以便后续可能再次读取）
    await file.seek(0)
    
    return file_url, file_id