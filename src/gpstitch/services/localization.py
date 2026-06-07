"""Small localization helpers for UI-facing backend metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from gpstitch.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def normalize_language(language: str | None) -> str:
    """Return a supported language code."""
    if language in SUPPORTED_LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


def t(key: str, language: str | None = None) -> str:
    """Translate a small set of backend-owned labels."""
    lang = normalize_language(language)
    return _TRANSLATIONS.get(lang, {}).get(key, _TRANSLATIONS["en"].get(key, key))


def localize_unit_options(unit_options: dict[str, dict[str, Any]], language: str | None = None) -> dict[str, dict[str, Any]]:
    """Localize unit option labels without changing values/defaults."""
    lang = normalize_language(language)
    localized = deepcopy(unit_options)
    if lang == "en":
        return localized

    category_labels = {
        "speed": "速度",
        "altitude": "海拔",
        "distance": "距离",
        "temperature": "温度",
    }
    option_labels = {
        "kph": "公里/小时",
        "mph": "英里/小时",
        "mps": "米/秒",
        "knot": "节",
        "metre": "米",
        "foot": "英尺",
        "km": "公里",
        "mile": "英里",
        "nmi": "海里",
        "degC": "摄氏度",
        "degF": "华氏度",
        "kelvin": "开尔文",
    }
    for name, category in localized.items():
        category["label"] = category_labels.get(name, category["label"])
        for option in category.get("options", []):
            option["label"] = option_labels.get(option["value"], option["label"])
    return localized


def localize_layout_name(name: str, display_name: str, language: str | None = None) -> str:
    """Localize layout display names while preserving layout IDs."""
    if normalize_language(language) == "en":
        return display_name
    if name.startswith("default-"):
        return "默认仪表盘"
    if name == "speed-awareness":
        return "速度感知"
    if name.startswith("dji-drone-"):
        return "DJI 飞行仪表盘"
    return display_name


def localize_map_style_name(style_name: str, display_name: str, language: str | None = None) -> str:
    """Localize known map style display names."""
    if normalize_language(language) == "en":
        return display_name
    known = {
        "amap-jsapi": "高德 JS API",
        "amap-jsapi-satellite": "高德卫星 + 路网",
        "amap-jsapi-mixed": "高德混合（上方普通 + 下方卫星）",
        "osm": "OpenStreetMap",
        "humanitarian": "OSM 人道主义",
        "cycle": "自行车地图",
        "transport": "交通地图",
        "landscape": "地形景观",
        "outdoors": "户外地图",
    }
    return known.get(style_name, display_name)


def localize_ffmpeg_profile(name: str, display_name: str, description: str, language: str | None = None) -> tuple[str, str]:
    """Localize FFmpeg profile metadata."""
    if normalize_language(language) == "en":
        return display_name, description
    profile_names = {
        "": "默认",
        "nvgpu": "NVIDIA GPU 加速",
        "nnvgpu": "NVIDIA GPU CUDA 叠加",
        "mov": "MOV 无损",
        "vp9": "VP9 透明通道",
        "vp8": "VP8 透明通道",
        "mac_hevc": "macOS HEVC 硬件编码",
        "mac": "macOS H.264 硬件编码",
        "qsv": "Intel QuickSync 加速",
    }
    profile_descriptions = {
        "": "H.264，veryfast 预设，兼顾速度和质量",
        "nvgpu": "NVIDIA GPU 硬件编码（H.264 / 25 Mbps）",
        "nnvgpu": "NVIDIA GPU + CUDA 叠加处理（H.264 / 25 Mbps）",
        "mov": "PNG 无损编码，文件较大",
        "vp9": "带透明通道的 VP9 编码",
        "vp8": "带透明通道的 VP8 编码",
        "mac_hevc": "macOS VideoToolbox HEVC，高质量",
        "mac": "macOS VideoToolbox H.264，高质量",
        "qsv": "Intel QuickSync HEVC 硬件加速",
    }
    return profile_names.get(name, display_name), profile_descriptions.get(name, description)


def localize_widget_metadata(widgets: list[Any], categories: list[str], language: str | None = None) -> tuple[list[Any], list[str]]:
    """Localize editor-visible widget metadata while preserving widget IDs and values."""
    if normalize_language(language) == "en":
        return list(widgets), list(categories)

    localized = []
    for widget in widgets:
        item = widget.model_copy(deep=True) if hasattr(widget, "model_copy") else deepcopy(widget)
        item.name = _WIDGET_NAMES_ZH.get(getattr(item, "type", ""), item.name)
        item.description = _WIDGET_DESCRIPTIONS_ZH.get(getattr(item, "type", ""), item.description)
        for prop in getattr(item, "properties", []) or []:
            prop.label = _PROPERTY_LABELS_ZH.get(prop.label, prop.label)
            prop.category = _PROPERTY_CATEGORIES_ZH.get(prop.category, prop.category)
            if prop.description:
                prop.description = _PROPERTY_DESCRIPTIONS_ZH.get(prop.description, prop.description)
            for option in prop.options or []:
                option.label = _OPTION_LABELS_ZH.get(option.label, option.label)
        localized.append(item)

    # Keep category identifiers stable because the editor groups by these values.
    return localized, list(categories)


_WIDGET_NAMES_ZH = {
    "text": "文本",
    "metric": "指标数值",
    "metric_unit": "指标单位标签",
    "datetime": "日期/时间",
    "icon": "图标",
    "moving_map": "移动地图",
    "journey_map": "全程地图",
    "moving_journey_map": "移动全程地图",
    "circuit_map": "赛道地图",
    "compass": "指南针",
    "compass_arrow": "指南针箭头",
    "bar": "条形指示器",
    "zone_bar": "分区条",
    "chart": "图表",
    "asi": "空速表",
    "msi": "速度表",
    "gps_lock_icon": "GPS 锁定图标",
    "composite": "组合容器",
    "translate": "位移容器",
    "frame": "边框容器",
    "cairo_circuit_map": "Cairo 赛道地图",
    "cairo_gauge_marker": "Cairo 指针仪表",
    "cairo_gauge_round_annotated": "Cairo 圆形标注仪表",
    "cairo_gauge_arc_annotated": "Cairo 弧形标注仪表",
    "cairo_gauge_donut": "Cairo 环形仪表",
}

_WIDGET_DESCRIPTIONS_ZH = {
    "text": "静态文本标签",
    "metric": "显示速度、海拔等遥测数值",
    "metric_unit": "显示指标的单位标签",
    "datetime": "显示视频日期和时间",
    "icon": "显示图片图标",
    "moving_map": "跟随当前位置的地图",
    "journey_map": "显示完整路线的地图",
    "moving_journey_map": "组合当前位置和完整路线的地图",
    "circuit_map": "显示赛道或线路布局的地图",
    "compass": "带方向指示的指南针",
    "compass_arrow": "简洁箭头指南针",
    "bar": "用于加速度等指标的水平条",
    "zone_bar": "带分区的渐变条",
    "chart": "某个指标的时间序列图表",
    "asi": "航空风格空速表",
    "msi": "马达/速度表风格仪表",
    "gps_lock_icon": "显示 GPS 信号状态的图标",
    "composite": "用于分组组件的容器",
    "translate": "带位置偏移的容器",
    "frame": "带背景的样式容器",
    "cairo_circuit_map": "高级赛道地图（需要 Cairo）",
    "cairo_gauge_marker": "带指针的弧形仪表（需要 Cairo）",
    "cairo_gauge_round_annotated": "带标注的圆形仪表（需要 Cairo）",
    "cairo_gauge_arc_annotated": "带标注的弧形仪表（需要 Cairo）",
    "cairo_gauge_donut": "环形仪表（需要 Cairo）",
}

_PROPERTY_CATEGORIES_ZH = {
    "Appearance": "外观",
    "Behavior": "行为",
    "Content": "内容",
    "Data": "数据",
    "General": "通用",
    "Position": "位置",
    "Size": "尺寸",
    "Speeds": "速度",
    "Zones": "分区",
}

_PROPERTY_LABELS_ZH = {
    "Alignment": "对齐方式",
    "Arc Length": "弧长",
    "Arrow Color": "箭头颜色",
    "Background Color": "背景颜色",
    "Bar Color": "条形颜色",
    "Corner Radius": "圆角半径",
    "Decimal Places": "小数位数",
    "Direction": "方向",
    "Fade Out": "淡出",
    "Fill Color": "填充颜色",
    "Fill Width": "填充宽度",
    "Filled": "填充",
    "Font Size": "字体大小",
    "Foreground Color": "前景颜色",
    "Format": "格式",
    "Green Zone Start": "绿色区起点",
    "Height": "高度",
    "Icon File": "图标文件",
    "Invert Colors": "反转颜色",
    "Line Color": "线条颜色",
    "Map Size": "地图尺寸",
    "Max Value": "最大值",
    "Metric": "指标",
    "Min Value": "最小值",
    "Opacity": "不透明度",
    "Outline Color": "描边颜色",
    "Outline Width": "描边宽度",
    "Rotate Map": "旋转地图",
    "Samples": "采样数",
    "Scale End": "刻度终点",
    "Show Needle": "显示指针",
    "Show Values": "显示数值",
    "Size": "大小",
    "Start Angle": "起始角度",
    "Text Color": "文本颜色",
    "Text Content": "文本内容",
    "Text Size": "文字大小",
    "Time Window (seconds)": "时间窗口（秒）",
    "Truncate": "截断",
    "Units": "单位",
    "Vfe": "Vfe",
    "Vne": "Vne",
    "Vno": "Vno",
    "Vs": "Vs",
    "Vs0": "Vs0",
    "Width": "宽度",
    "X Position": "X 位置",
    "Y Position": "Y 位置",
    "Yellow Zone Start": "黄色区起点",
    "Zone 0 Color": "分区 0 颜色",
    "Zone 1 Color": "分区 1 颜色",
    "Zone 1 Threshold": "分区 1 阈值",
    "Zone 2 Color": "分区 2 颜色",
    "Zone 2 Threshold": "分区 2 阈值",
    "Zone 3 Color": "分区 3 颜色",
    "Zone 3 Threshold": "分区 3 阈值",
    "Zoom Level": "缩放级别",
}

_OPTION_LABELS_ZH = {
    "Acceleration": "加速度",
    "Acceleration X": "X 轴加速度",
    "Acceleration Y": "Y 轴加速度",
    "Acceleration Z": "Z 轴加速度",
    "Altitude": "海拔",
    "Altitude (user setting)": "海拔（用户设置）",
    "Azimuth": "方位角",
    "Cadence": "踏频",
    "Calculated Gradient": "计算坡度",
    "Calculated Odometer": "计算里程",
    "Calculated Speed": "计算速度",
    "Center": "居中",
    "Course Over Ground": "地面航向",
    "Degrees (бу)": "度",
    "Distance": "距离",
    "Distance (user setting)": "距离（用户设置）",
    "Feet": "英尺",
    "G-force": "G 力",
    "GPS DOP": "GPS DOP",
    "GPS Lock": "GPS 锁定",
    "Gear Front": "前齿盘",
    "Gear Rear": "后飞轮",
    "Gradient": "坡度",
    "Gravity X": "X 轴重力",
    "Gravity Y": "Y 轴重力",
    "Gravity Z": "Z 轴重力",
    "Heart Rate": "心率",
    "Knots": "节",
    "Latitude": "纬度",
    "Left": "左",
    "Left to Right": "从左到右",
    "Longitude": "经度",
    "Metres": "米",
    "Miles": "英里",
    "None": "无",
    "Odometer": "里程计",
    "Orientation Pitch": "俯仰角",
    "Orientation Roll": "横滚角",
    "Orientation Yaw": "偏航角",
    "Pace": "配速",
    "Pace (km)": "配速（公里）",
    "Pace (mile)": "配速（英里）",
    "Power": "功率",
    "Respiration": "呼吸频率",
    "Right": "右",
    "Speed": "速度",
    "Speed (user setting)": "速度（用户设置）",
    "Temperature": "温度",
    "Temperature (user setting)": "温度（用户设置）",
    "Top to Bottom": "从上到下",
    "km/h": "公里/小时",
    "mph": "英里/小时",
}

_PROPERTY_DESCRIPTIONS_ZH = {
    "Metric to display": "要显示的指标",
    "Units for the metric": "指标使用的单位",
}


_TRANSLATIONS = {
    "en": {
        "picker_unavailable": "Native picker is unavailable. You can enter the path manually.",
        "picker_cancelled": "Selection cancelled.",
        "local_mode_disabled": "Local file mode is disabled.",
        "directory_not_found": "Directory not found.",
        "not_a_directory": "Not a directory.",
        "no_supported_videos": "No supported video files were found.",
        "batch_directory_loaded": "Batch directory loaded.",
        "map_cache_no_route": "No route data is available for map cache warmup.",
        "map_cache_warmed": "Map cache warmup completed.",
        "map_cache_partial": "Map cache warmup was capped; only part of the route was pre-cached.",
        "map_cache_failed": "Map cache warmup failed.",
    },
    "zh-CN": {
        "picker_unavailable": "无法打开本机选择器。你仍然可以手动输入路径。",
        "picker_cancelled": "已取消选择。",
        "local_mode_disabled": "本机文件模式已禁用。",
        "directory_not_found": "目录不存在。",
        "not_a_directory": "这不是一个目录。",
        "no_supported_videos": "未找到支持的视频文件。",
        "batch_directory_loaded": "已加载批量目录。",
        "map_cache_no_route": "没有可用于地图缓存预热的轨迹数据。",
        "map_cache_warmed": "地图缓存预热完成。",
        "map_cache_partial": "地图缓存预热已达到上限，仅预缓存部分轨迹。",
        "map_cache_failed": "地图缓存预热失败。",
    },
}
