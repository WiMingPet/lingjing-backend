"""
电商商品套图路由
"""
import os
import json
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.task import APIResponse
from app.utils.file_utils import upload_file_helper
from app.services.merchant_service import MerchantService
from app.utils.credits import check_and_deduct_credits
from app.data.prices import get_merchant_cost
from app.rq_app import queue_other
from app.tasks.other_tasks import generate_merchant_task

router = APIRouter(prefix="/merchant", tags=["电商商品套图"])

# ========== 是否使用异步模式 ==========
USE_ASYNC = os.getenv("USE_ASYNC", "false").lower() == "true"
print(f"[MERCHANT] USE_ASYNC = {USE_ASYNC}")
# =====================================


@router.post("/generate_package", response_model=APIResponse)
async def generate_package(
    images: List[UploadFile] = File(...),
    template: str = Form(...),
    product_type: str = Form("other"),
    height: int = Form(None),
    weight: int = Form(None),
    scene_count: int = Form(1),
    gender: str = Form("female"),
    scene_text: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.data.merchant_templates import TEMPLATE_MODELS

    if template not in TEMPLATE_MODELS:
        raise HTTPException(status_code=400, detail="模板不存在")

    # ========== 计算扣费 ==========
    cost = get_merchant_cost(template, scene_count)
    if cost <= 0:
        raise HTTPException(status_code=400, detail="无效的扣费金额")

    # ========== 上传图片 ==========
    cloth_urls = []
    for img in images:
        cloth_url, _ = await upload_file_helper(img, "merchant/products")
        cloth_urls.append(cloth_url)
        print(f"[DEBUG] 商品图片已上传: {cloth_url}")

    # ========== 图片安全审核 ==========
    from app.services.image_service import ImageService
    for cloth_url in cloth_urls:
        if not await ImageService.check_image_safety(cloth_url):
            raise HTTPException(status_code=400, detail="商品图片未通过安全审核，请更换图片")

    # ========== 构建请求数据 ==========
    request_data = {
        "cloth_urls": cloth_urls,
        "template": template,
        "product_type": product_type,
        "height": height,
        "weight": weight,
        "scene_count": scene_count,
        "gender": gender,
        "scene_text": scene_text,
    }

    user = current_user
    user_id = current_user.id

    # ========== 判断模式 ==========
    if USE_ASYNC:
        # ========== 异步模式 ==========
        print(f"[MERCHANT] 使用异步模式")

        if queue_other is None:
            raise HTTPException(status_code=500, detail="异步队列未初始化，请检查Redis连接")

        # 先扣费
        check_and_deduct_credits(user, db, cost, "电商商品套图")

        # 创建任务
        from app.models.task import Task
        task = Task(
            user_id=user_id,
            task_type="merchant",
            status="pending",
            input_data=request_data,
            credits_cost=cost,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # 提交队列
        job = queue_other.enqueue(generate_merchant_task, task.id, user_id, request_data)
        print(f"[MERCHANT] RQ 任务已提交: task_id={task.id}, job_id={job.id}")

        return APIResponse(
            code=200,
            message="电商套图任务已提交，预计3-10分钟完成",
            data={
                "task_id": task.id,
                "status": "pending",
                "async": True
            }
        )
    else:
        # ========== 同步模式（原有逻辑） ==========
        print(f"[MERCHANT] 使用同步模式")

        from app.services.kling import kling_service
        from app.data.merchant_templates import MODEL_IMAGES

        # 生成前检查余额
        if user.credits < cost:
            raise HTTPException(status_code=403, detail=f"灵境点不足，需要{cost}点，当前{user.credits}点")

        # 调用生成逻辑（抽出为独立函数）
        results = await _generate_package_logic(
            cloth_urls=cloth_urls,
            template=template,
            product_type=product_type,
            height=height,
            weight=weight,
            scene_count=scene_count,
            gender=gender,
            scene_text=scene_text,
        )

        # 生成成功后扣费
        check_and_deduct_credits(user, db, cost, "电商商品套图")

        # 保存历史记录
        from app.models.history import History
        for item in results:
            all_images = []
            all_images.extend(item.get("tryon_images", []))
            all_images.extend(item.get("main_images", []))
            all_images.extend(item.get("scene_images", []))
            if item.get("video_url"):
                all_images.append(item.get("video_url"))

            if all_images:
                history = History(
                    user_id=user_id,
                    url=json.dumps(all_images),
                    type="电商商品套图",
                    thumbnail=all_images[0],
                )
                db.add(history)

        db.commit()

        return APIResponse(
            code=200,
            message="生成成功",
            data={"results": results}
        )


# ========== 抽出生成逻辑（供同步和异步共用） ==========
async def _generate_package_logic(
    cloth_urls: List[str],
    template: str,
    product_type: str,
    height: int,
    weight: int,
    scene_count: int,
    gender: str,
    scene_text: str,
) -> List[dict]:
    """生成电商套图的核心逻辑"""
    from app.services.kling import kling_service
    from app.data.merchant_templates import TEMPLATE_MODELS, MODEL_IMAGES
    from app.services.oss_service import oss_service

    template_data = TEMPLATE_MODELS[template]
    results = []

    for cloth_url in cloth_urls:
        result_item = {"cloth_url": cloth_url}

        if product_type == "clothing":
            # 服装类
            model_image = MODEL_IMAGES.get(gender, MODEL_IMAGES["female"])
            tryon_images = []
            try:
                tryon_task_id = kling_service.generate_tryon(
                    human_image_url=model_image,
                    cloth_image_url=cloth_url,
                )
                tryon_result = kling_service.wait_for_tryon_result(tryon_task_id, max_wait=120)
                tryon_images = [
                    img_data.get("url", "")
                    for img_data in tryon_result.get("task_result", {}).get("images", [])
                ]
                result_item["tryon_images"] = tryon_images[:1]
            except Exception as e:
                print(f"[DEBUG] 试穿失败: {e}")
                result_item["tryon_images"] = []

            # 白底主图
            if template == "white_bg":
                try:
                    main_task_id = kling_service.generate_image(
                        prompt="电商商品图，纯白背景RGB255,255,255，产品居中，无阴影，高清细节",
                        reference_image_url=cloth_url,
                    )
                    main_result = kling_service.wait_for_result(main_task_id, "image", max_wait=120)
                    main_images = [
                        img_data.get("url", "")
                        for img_data in main_result.get("task_result", {}).get("images", [])
                    ]

                    if main_images:
                        white_bg_bytes = MerchantService.force_white_background(main_images[0])
                        if white_bg_bytes:
                            oss_url = await oss_service.upload_file(
                                white_bg_bytes,
                                "jpg",
                                "merchant/white_bg"
                            )
                            result_item["main_images"] = [oss_url]
                        else:
                            result_item["main_images"] = main_images[:1]
                except Exception as e:
                    print(f"[DEBUG] 白底图生成失败: {e}")
                    result_item["main_images"] = []

            # 场景图
            if template == "scene":
                result_item["scene_images"] = []
                scenes = ["简约场景", "自然光场景", "生活场景", "时尚场景", "家居场景", "街拍场景"]
                scene_texts = MerchantService.split_scene_texts(scene_text, scene_count)

                for i in range(scene_count):
                    scene = scenes[i % len(scenes)]
                    prompt = f"服装模特图，{scene}，简约时尚场景，电商风格，无文字"

                    try:
                        scene_task_id = kling_service.generate_image(
                            prompt=prompt,
                            reference_image_url=tryon_images[0] if tryon_images else cloth_url,
                        )
                        scene_result = kling_service.wait_for_result(scene_task_id, "image", max_wait=120)
                        imgs = [
                            img_data.get("url", "")
                            for img_data in scene_result.get("task_result", {}).get("images", [])
                        ]

                        if imgs:
                            if scene_texts[i]:
                                text_image_bytes = MerchantService.add_text_to_image(
                                    imgs[0],
                                    scene_texts[i],
                                    position="bottom"
                                )
                                if text_image_bytes:
                                    oss_url = await oss_service.upload_file(
                                        text_image_bytes,
                                        "jpg",
                                        "merchant/scene_with_text"
                                    )
                                    result_item["scene_images"].append(oss_url)
                                else:
                                    result_item["scene_images"].extend(imgs[:1])
                            else:
                                result_item["scene_images"].extend(imgs[:1])
                    except Exception as e:
                        print(f"[DEBUG] 场景图{i+1}失败: {e}")

        else:
            # 其他商品
            prompt = f"电商商品图，{template_data['prompt_suffix']}"
            try:
                image_task_id = kling_service.generate_image(
                    prompt=prompt,
                    reference_image_url=cloth_url,
                )
                image_result = kling_service.wait_for_result(image_task_id, "image", max_wait=120)
                result_item["main_images"] = [
                    img_data.get("url", "")
                    for img_data in image_result.get("task_result", {}).get("images", [])
                ][:1]
            except Exception as e:
                result_item["main_images"] = []

            if template == "scene":
                result_item["scene_images"] = []
                scenes = ["简约场景", "自然光场景", "生活场景", "商务场景", "时尚场景", "家居场景"]
                scene_texts = MerchantService.split_scene_texts(scene_text, scene_count)

                for i in range(scene_count):
                    scene = scenes[i % len(scenes)]
                    prompt = f"电商商品图，{scene}，{template_data['prompt_suffix']}，无文字"

                    try:
                        scene_task_id = kling_service.generate_image(
                            prompt=prompt,
                            reference_image_url=cloth_url,
                        )
                        scene_result = kling_service.wait_for_result(scene_task_id, "image", max_wait=120)
                        imgs = [
                            img_data.get("url", "")
                            for img_data in scene_result.get("task_result", {}).get("images", [])
                        ]

                        if imgs:
                            if scene_texts[i]:
                                text_image_bytes = MerchantService.add_text_to_image(
                                    imgs[0],
                                    scene_texts[i],
                                    position="bottom"
                                )
                                if text_image_bytes:
                                    oss_url = await oss_service.upload_file(
                                        text_image_bytes,
                                        "jpg",
                                        "merchant/scene_with_text"
                                    )
                                    result_item["scene_images"].append(oss_url)
                                else:
                                    result_item["scene_images"].extend(imgs[:1])
                            else:
                                result_item["scene_images"].extend(imgs[:1])
                    except Exception as e:
                        print(f"[DEBUG] 场景图{i+1}失败: {e}")

        if product_type == "clothing" and height and weight:
            result_item["size_table"] = MerchantService.generate_size_table(height, weight)

        results.append(result_item)

    return results

@router.get("/task/{task_id}", response_model=APIResponse)
def get_merchant_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取电商套图任务状态"""
    from app.models.task import Task
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return APIResponse(
        code=200,
        message="获取成功",
        data={
            "task_id": task.id,
            "status": task.status,
            "output_data": task.output_data,
            "error_message": task.error_message,
        }
    )