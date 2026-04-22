"""
文件上传工具
"""
import uuid
import os
import io
import time
from app.services.oss_service import oss_service
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


async def upload_file_helper(file, folder: str, filename: str = None) -> tuple:
    """
    上传文件到 OSS
    
    参数:
        file: 文件对象（支持同步/异步）或文件路径字符串或 bytes
        folder: OSS 文件夹名称
        filename: 可选，指定文件名（不传则自动生成或从 file 对象获取）
    
    返回:
        (url, file_id)
    """
    # 1. 获取文件名
    if filename:
        final_filename = filename
    elif hasattr(file, 'filename'):
        final_filename = file.filename
    elif hasattr(file, 'name'):
        final_filename = os.path.basename(file.name)
    else:
        # 自动生成文件名
        ext = "bin"
        if hasattr(file, 'name') and '.' in file.name:
            ext = file.name.split('.')[-1]
        final_filename = f"{folder}_{int(time.time())}.{ext}"
    
    # 2. 读取文件内容
    content = None
    if hasattr(file, 'read'):
        # 文件对象
        try:
            content = await file.read()
        except TypeError:
            # 同步读取
            content = file.read()
        except AttributeError:
            # 没有 read 方法，尝试直接使用
            content = file
    elif isinstance(file, bytes):
        content = file
    elif isinstance(file, str):
        # 文件路径
        with open(file, 'rb') as f:
            content = f.read()
    else:
        content = file
    
    if content is None:
        raise ValueError("无法读取文件内容")
    
    # 3. 对于图片，转换为 JPEG 格式
    if final_filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
        try:
            content, final_filename = await convert_to_supported_format(content, final_filename)
        except Exception as e:
            print(f"图片转换失败: {e}")
    
    # 4. 上传到 OSS
    file_url = await oss_service.upload_file(content, final_filename, folder)
    
    return file_url, final_filename