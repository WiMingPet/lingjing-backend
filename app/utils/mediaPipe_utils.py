"""
MediaPipe 工具函数
用于从图片中提取人体特征点
"""
import cv2
import numpy as np
from typing import Optional, Dict, List, Tuple
import mediapipe as mp

# MediaPipe 解决方案
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils


class MediaPipeProcessor:
    """MediaPipe 处理器"""

    def __init__(self):
        self.pose = mp_pose.Pose(
            static_image_mode=True,
            model_complexity=2,
            enable_segmentation=False,
            min_detection_confidence=0.5
        )

    def extract_body_landmarks(self, image_path: str) -> Optional[Dict]:
        """
        从图片中提取身体关键点

        Returns:
            Dict: 包含关键点坐标的字典
        """
        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            return None

        # 转换为RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # 处理
        results = self.pose.process(image_rgb)

        if not results.pose_landmarks:
            return None

        # 提取关键点
        landmarks = {}
        h, w = image.shape[:2]

        for idx, landmark in enumerate(results.pose_landmarks.landmark):
            landmarks[idx] = {
                "x": landmark.x,
                "y": landmark.y,
                "z": landmark.z,
                "visibility": landmark.visibility
            }

        return {
            "landmarks": landmarks,
            "image_width": w,
            "image_height": h
        }

    def calculate_body_measurements(self, landmarks: Dict, image_height: float, image_width: float) -> Dict:
        """
        根据关键点计算身体尺寸

        Returns:
            Dict: 身体尺寸 (单位: cm)
        """
        # 关键点索引
        LEFT_SHOULDER = 11
        RIGHT_SHOULDER = 12
        LEFT_HIP = 23
        RIGHT_HIP = 24
        LEFT_KNEE = 25
        RIGHT_KNEE = 26
        LEFT_ANKLE = 27
        RIGHT_ANKLE = 28
        NOSE = 0
        LEFT_ELBOW = 13
        RIGHT_ELBOW = 14
        LEFT_WRIST = 15
        RIGHT_WRIST = 16

        def get_point(idx):
            return (landmarks[idx]["x"] * image_width, landmarks[idx]["y"] * image_height)

        # 计算肩膀宽度 (cm) - 假设图片宽度对应100cm
        shoulder_width_px = abs(get_point(RIGHT_SHOULDER)[0] - get_point(LEFT_SHOULDER)[0])
        shoulder_width = (shoulder_width_px / image_width) * 100

        # 计算身高 (像素 -> cm, 假设全身高度对应170cm)
        nose_y = get_point(NOSE)[1]
        ankle_y = max(get_point(LEFT_ANKLE)[1], get_point(RIGHT_ANKLE)[1])
        height_px = ankle_y - nose_y
        height = (height_px / image_height) * 170

        # 计算腰围
        hip_width_px = abs(get_point(RIGHT_HIP)[0] - get_point(LEFT_HIP)[0])
        waist_circumference = (hip_width_px / image_width) * 80

        # 计算臀围
        hip_circumference = waist_circumference * 1.1

        # 计算胸围 (基于肩膀宽度)
        bust_circumference = shoulder_width * 1.5

        # 估算体重 (基于身高和体态)
        # 这里使用简化公式
        weight = height * 0.5  # 简化估算

        return {
            "height": round(height, 1),
            "weight": round(weight, 1),
            "shoulder_width": round(shoulder_width, 1),
            "bust": round(bust_circumference, 1),
            "waist": round(waist_circumference, 1),
            "hip": round(hip_circumference, 1)
        }

    def process_full_body_image(self, image_path: str) -> Optional[Dict]:
        """
        处理全身照，返回尺寸数据
        """
        result = self.extract_body_landmarks(image_path)
        if result is None:
            return None

        measurements = self.calculate_body_measurements(
            result["landmarks"],
            result["image_height"],
            result["image_width"]
        )

        return measurements


# 随机森林模型预测尺码
class SizePredictor:
    """
    尺码预测器
    使用预加载的随机森林模型
    """

    def __init__(self):
        """
        初始化模型
        生产环境应加载真实模型文件
        """
        # 模拟加载随机森林模型
        # 实际实现:
        # import joblib
        # self.model = joblib.load("models/size_predictor.pkl")
        self.is_loaded = True

    def predict_size(self, measurements: Dict, gender: str = "unisex", clothing_type: str = "general") -> Tuple[str, float]:
        """
        预测尺码

        Args:
            measurements: 身体尺寸 {height, weight, bust, waist, hip}
            gender: 性别
            clothing_type: 服装类型

        Returns:
            (尺码, 置信度)
        """
        # Mock实现 - 使用规则简单预测
        # 实际应使用训练好的模型预测

        height = measurements.get("height", 170)
        waist = measurements.get("waist", 80)
        bust = measurements.get("bust", 90)

        # 简单的尺码规则
        if clothing_type == "shirt":
            if bust < 85:
                size = "S"
            elif bust < 95:
                size = "M"
            elif bust < 105:
                size = "L"
            else:
                size = "XL"
        elif clothing_type == "pants":
            if waist < 70:
                size = "S"
            elif waist < 80:
                size = "M"
            elif waist < 90:
                size = "L"
            else:
                size = "XL"
        elif clothing_type == "dress":
            if bust < 85 and waist < 65:
                size = "S"
            elif bust < 95 and waist < 75:
                size = "M"
            elif bust < 105 and waist < 85:
                size = "L"
            else:
                size = "XL"
        else:  # general
            if height < 160:
                size = "S"
            elif height < 170:
                size = "M"
            elif height < 180:
                size = "L"
            else:
                size = "XL"

        # 返回尺码和置信度 (模拟)
        confidence = 0.85

        return size, confidence

    def predict_with_confidence(self, measurements: Dict, gender: str = "unisex", clothing_type: str = "general") -> Dict:
        """
        预测尺码，返回详细信息
        """
        size, confidence = self.predict_size(measurements, gender, clothing_type)

        return {
            "height": measurements.get("height", 0),
            "weight": measurements.get("weight", 0),
            "bust": measurements.get("bust", 0),
            "waist": measurements.get("waist", 0),
            "hip": measurements.get("hip", 0),
            "recommended_size": size,
            "confidence": confidence
        }
