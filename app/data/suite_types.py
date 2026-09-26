from enum import Enum


class SuiteType(str, Enum):
    WHITE_BG = "white_bg"
    SCENE = "scene"
    PREMIUM_APLUS = "premium_aplus"
    STANDARD_APLUS = "standard_aplus"
    PHONE_APLUS = "phone_aplus"


SUITE_CANVAS = {
    "white_bg":       {"width": 1024, "height": 1024},
    "scene":          {"width": 1024, "height": 1024},
    "premium_aplus":  {"width": 1464, "height": 600},
    "standard_aplus": {"width": 970,  "height": 600},
    "phone_aplus":    {"width": 600,  "height": 450},
}

SUITE_MODULES = {
    "white_bg":       ["white_bg"],
    "scene":          ["scene_01", "scene_02", "scene_03", "scene_04", "scene_05", "scene_06"],
    "premium_aplus":  ["premium_01", "premium_02", "premium_03", "premium_04", "premium_05", "premium_06"],
    "standard_aplus": ["standard_01", "standard_02", "standard_03", "standard_04", "standard_05", "standard_06"],
    "phone_aplus":    ["phone_01", "phone_02", "phone_03", "phone_04", "phone_05", "phone_06"],
}

SUITE_COST = {
    "white_bg": 10,
    "scene": 15,
    "premium_aplus": 50,
    "standard_aplus": 30,
    "phone_aplus": 20,
}