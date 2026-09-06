"""
电商商品套图路由
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.models.user import User
from app.utils.auth import get_current_user
from app.schemas.task import APIResponse
from app.utils.file_utils import upload_file_helper
from app.services.merchant_service import MerchantService

router = APIRouter(prefix="/merchant", tags=["电商商品套图"])


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
    from app.services.kling import kling_service
    from app.data.merchant_templates import TEMPLATE_MODELS, MODEL_IMAGES

    if template not in TEMPLATE_MODELS:
        raise HTTPException(status_code=400, detail="模板不存在")

    template_data = TEMPLATE_MODELS[template]
    results = []

    # ========== 扣费 ==========
    cost = 0
    if template == "white_bg":
        cost += 10
    if template == "scene":
        cost += scene_count * 10
    if current_user.credits < cost:
        raise HTTPException(status_code=403, detail=f"灵境点不足，需要{cost}点，当前{current_user.credits}点")
    current_user.credits -= cost
    db.commit()
    # ======================

    for img in images:
        cloth_url, _ = await upload_file_helper(img, "merchant/products")
        result_item = {"cloth_url": cloth_url}

        # ========== 图片安全审核 ==========
        from app.services.image_service import ImageService
        if not await ImageService.check_image_safety(cloth_url):
            raise HTTPException(status_code=400, detail="商品图片未通过安全审核，请更换图片")

        if product_type == "clothing":
            # 服装：指定模特虚拟试穿
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
                        prompt="电商商品图，白色背景，产品居中，高清细节",
                        reference_image_url=cloth_url,
                    )
                    main_result = kling_service.wait_for_result(main_task_id, "image", max_wait=120)
                    result_item["main_images"] = [
                        img_data.get("url", "")
                        for img_data in main_result.get("task_result", {}).get("images", [])
                    ][:1]
                except Exception as e:
                    result_item["main_images"] = []

            # 场景图多张（服装类，支持文案拆分）
            if template == "scene":
                result_item["scene_images"] = []
                scenes = ["简约场景", "自然光场景", "生活场景", "时尚场景", "家居场景", "街拍场景"]
                scene_texts = MerchantService.split_scene_texts(scene_text, scene_count)

                for i in range(scene_count):
                    scene = scenes[i % len(scenes)]
                    if scene_texts[i]:
                        prompt = f"服装模特图，{scene}，图片中清晰显示文字：{scene_texts[i]}，排版美观，突出卖点"
                    else:
                        prompt = f"服装模特图，{scene}，简约时尚场景，电商风格"
                    try:
                        scene_task_id = kling_service.generate_image(
                            prompt=prompt,
                            reference_image_url=tryon_images[0] if tryon_images else cloth_url,
                        )
                        scene_result = kling_service.wait_for_result(scene_task_id, "image", max_wait=120)
                        imgs = [
                            img_data.get("url", "")
                            for img_data in scene_result.get("task_result", {}).get("images", [])
                        ][:1]
                        result_item["scene_images"].extend(imgs)
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

                # 拆分/优化文案
                scene_texts = MerchantService.split_scene_texts(scene_text, scene_count)

                for i in range(scene_count):
                    scene = scenes[i % len(scenes)]
                    if scene_texts[i]:
                        prompt = f"电商营销场景图，商品展示在{scene}中，图片中清晰显示文字：{scene_texts[i]}，排版美观，突出卖点，专业设计"
                    else:
                        prompt = f"电商商品图，{scene}，{template_data['prompt_suffix']}"
                    try:
                        scene_task_id = kling_service.generate_image(
                            prompt=prompt,
                            reference_image_url=cloth_url,
                        )
                        scene_result = kling_service.wait_for_result(scene_task_id, "image", max_wait=120)
                        imgs = [
                            img_data.get("url", "")
                            for img_data in scene_result.get("task_result", {}).get("images", [])
                        ][:1]
                        result_item["scene_images"].extend(imgs)
                    except Exception as e:
                        print(f"[DEBUG] 场景图{i+1}失败: {e}")

        if product_type == "clothing" and height and weight:
            result_item["size_table"] = MerchantService.generate_size_table(height, weight)

        results.append(result_item)

    # ========== 保存历史记录 ==========
    import json
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
                user_id=current_user.id,
                url=json.dumps(all_images),
                type="电商商品套图",
                thumbnail=all_images[0],
            )
            db.add(history)

    db.commit()
    # ==========================

    return APIResponse(
        code=200,
        message="生成成功",
        data={"results": results}
    )