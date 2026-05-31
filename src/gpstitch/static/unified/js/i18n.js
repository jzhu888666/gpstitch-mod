/**
 * Lightweight Chinese/English localization.
 * Internal API values and persisted config keys are intentionally unchanged.
 */

(function () {
    const STORAGE_KEY = 'gpstitch_language';
    const DEFAULT_LANGUAGE = 'zh-CN';
    const SUPPORTED = new Set(['zh-CN', 'en']);

    const zh = {
        'Quick Mode': '快速模式',
        'Advanced Mode': '高级模式',
        'Export XML': '导出 XML',
        'Batch Render': '批量渲染',
        'Render Video': '渲染视频',
        'Get Command': '获取命令',
        'Files': '文件',
        'Widgets': '组件',
        'Search widgets...': '搜索组件...',
        'Layout:': '布局:',
        'Undo': '撤销',
        'Redo': '重做',
        'Zoom Out': '缩小',
        'Zoom In': '放大',
        'Fit to View': '适应视图',
        'Fit': '适应',
        'Grid': '网格',
        'Snap': '吸附',
        'Canvas:': '画布:',
        'Template:': '模板:',
        '-- Select Template --': '-- 选择模板 --',
        'Save': '保存',
        'Upload': '上传',
        'Manage': '管理',
        'Auto': '自动',
        'Refresh': '刷新',
        'No preview available': '暂无预览',
        'Upload a file and select a layout to see preview': '加载文件并选择布局后查看预览',
        'Generating preview...': '正在生成预览...',
        "Canvas size doesn't match video resolution.": '画布尺寸与视频分辨率不一致。',
        'Resize canvas to': '调整画布为',
        'Canvas is empty': '画布为空',
        'Drag widgets from the left panel': '从左侧面板拖入组件',
        'or select a template above': '或在上方选择模板',
        'Start': '开始',
        'End': '结束',
        'Config': '配置',
        'Properties': '属性',
        'Layers': '图层',
        'Speed Unit': '速度单位',
        'Altitude Unit': '海拔单位',
        'Distance': '距离',
        'Temperature': '温度',
        'Map Style': '地图样式',
        'FFmpeg Profile': 'FFmpeg 配置',
        'GPS filters remove bad data points (jumps, glitches)': 'GPS 过滤会移除异常点（跳点、毛刺）',
        'GPS DOP Max': 'GPS DOP 上限',
        'GPS Speed Max (km/h)': 'GPS 速度上限 (km/h)',
        'Filter unrealistic speed spikes': '过滤不真实的速度尖峰',
        'Select a widget to edit its properties': '选择一个组件以编辑属性',
        'No widgets on canvas': '画布上没有组件',
        'Ready': '就绪',
        'Frame: --': '帧: --',
        'CLI Command': 'CLI 命令',
        'Run this command in your terminal to render the video:': '在终端运行以下命令来渲染视频:',
        'Copy to Clipboard': '复制到剪贴板',
        'Video': '视频',
        'MP4 (optional)': 'MP4（可选）',
        'GPS Data': 'GPS 数据',
        'GPX/FIT/SRT (optional)': 'GPX/FIT/SRT（可选）',
        'Load': '加载',
        'Browse': '选择',
        'Select': '选择',
        'Choose': '选择',
        'Drop MP4/MOV or click': '拖入 MP4/MOV 或点击',
        'Drop GPX/FIT/SRT or click': '拖入 GPX/FIT/SRT 或点击',
        'Remove': '移除',
        'Merge Mode': '合并模式',
        'Video Mode': '视频模式',
        'GPS Only': '仅 GPS',
        'Using embedded GPS': '使用内置 GPS',
        'Video + external GPS': '视频 + 外部 GPS',
        'Overlay without video': '无视频叠加',
        'Batch Render Progress': '批量渲染进度',
        'Shared GPX/FIT Track': '共享 GPX/FIT 轨迹',
        '(optional)': '（可选）',
        'Single GPS track applied to all videos (e.g., Garmin watch recording)': '一个 GPS 轨迹应用到所有视频（例如 Garmin 手表记录）',
        'Time Offset': '时间偏移',
        '(seconds)': '（秒）',
        'Adjust time alignment between video and GPS track': '调整视频与 GPS 轨迹之间的时间对齐',
        'File Paths': '文件路径',
        'Files to process:': '待处理文件:',
        'Pre-checks': '预检查',
        'Check for existing output files and GPS quality issues before starting': '开始前检查输出文件冲突和 GPS 质量问题',
        'Analyzing files...': '正在分析文件...',
        'Pending: 0': '等待: 0',
        'Running: 0': '运行: 0',
        'Completed: 0': '完成: 0',
        'Failed: 0': '失败: 0',
        'Current Job:': '当前任务:',
        'Frame:': '帧:',
        'Speed:': '速度:',
        'ETA:': '预计剩余:',
        'Log Output': '日志输出',
        'Hide': '隐藏',
        'Show': '显示',
        'Cancel': '取消',
        'Close': '关闭',
        'Start Batch Render': '开始批量渲染',
        'Select Video Folder': '选择视频目录',
        'Select Shared GPS': '选择共享 GPS',
        'GPS Quality Check': 'GPS 质量检查',
        'Filename': '文件名',
        'Status': '状态',
        'Usable': '可用率',
        'DOP Avg': '平均 DOP',
        'Source': '来源',
        'Skip Poor GPS': '跳过低质量 GPS',
        'Continue': '继续',
        'Overwrite': '覆盖',
        'Skip Existing': '跳过已存在',
        'Language': '语言',
        '中文': '中文',
        'English': 'English',
        'Loading...': '正在加载...',
        'Session restored': '会话已恢复',
        'XML exported': 'XML 已导出',
        'Exporting...': '正在导出...',
        'Preview failed': '预览失败',
        'Preview at': '预览时间',
        'No GPS data found': '未找到 GPS 数据',
        'File not found': '文件不存在',
        'Command copied to clipboard': '命令已复制到剪贴板',
        'Failed to copy command to clipboard': '复制命令失败',
        'Initialization Failed': '初始化失败',
        'Preview Failed': '预览失败',
        'No File Uploaded': '未加载文件',
        'Template Not Found': '模板不存在',
        'No Template Selected': '未选择模板',
        'Command Generation Failed': '命令生成失败',
        'Export Failed': '导出失败',
        'Export Not Available': '无法导出',
        'API Key Required': '需要 API Key',
        'Use OSM': '使用 OSM',
        'GPS Data Missing': '缺少 GPS 数据',
        'File Not Found': '文件不存在',
        'Re-upload': '重新上传',
        'Copy Failed': '复制失败',
        'No Files': '没有文件',
        'Batch Render Failed': '批量渲染失败',
        'Batch Cancelled': '批量已取消',
        'No Files to Process': '没有可处理文件',
        'Files Skipped': '已跳过文件',
        'All Files Skipped': '所有文件已跳过',
        'Some Files Skipped': '部分文件已跳过',
        'Batch Started': '批量已开始',
        'Batch Complete': '批量完成',
        'Batch Directory': '批量目录',
        'Directory Picker Failed': '目录选择失败',
        'File Picker Failed': '文件选择失败',
        'Native picker is unavailable. You can enter the path manually.': '无法打开本机选择器。你仍然可以手动输入路径。',
        'Map Cache': '地图缓存',
        'Enter file paths, one per line.': '每行输入一个文件路径。',
        'For video + GPX/FIT pairs, separate with comma.': '视频 + GPX/FIT 成对输入时，用逗号分隔。',
        'Enter video file paths, one per line.': '每行输入一个视频文件路径。',
        'Per-file GPX pairs are ignored when shared GPX is set.': '设置共享 GPX 后，将忽略逐文件 GPX 配对。',
        'Format: video.mp4 (one per line)': '格式：video.mp4（每行一个）',
        'Format: video.mp4 or video.mp4, track.gpx': '格式：video.mp4 或 video.mp4, track.gpx',
        'Rendering Video': '正在渲染视频',
        'Preparing...': '正在准备...',
        'Waiting to start...': '等待开始...',
        'Completed!': '已完成！',
        'Done': '完成',
        'Failed to start render': '启动渲染失败',
        'Failed to cancel render': '取消渲染失败',
        'Are you sure you want to cancel this render?': '确定要取消本次渲染吗？',
        'Connection lost. Check server status.': '连接已断开，请检查服务状态。',
        'Unknown error': '未知错误',
        'Frame': '帧',
        'Text': '文本',
        'Metrics': '指标',
        'Maps': '地图',
        'Gauges': '仪表',
        'Charts': '图表',
        'Indicators': '指示器',
        'Containers': '容器',
        'Cairo': 'Cairo',
        'No layout loaded': '未加载布局',
        'No widgets in layout': '布局中没有组件',
        'No widgets match your search': '没有匹配的组件',
        'Unknown widget type': '未知组件类型',
        'Pending': '等待中',
        'Running': '运行中',
        'Completed': '已完成',
        'Failed': '失败',
        'Cancelled': '已取消',
        'Delete': '删除',
        'Lock': '锁定',
        'Unlock': '解锁',
        'Files Already Exist': '文件已存在',
        'The following files will be overwritten:': '以下文件将被覆盖:',
        'Overwrite All': '全部覆盖',
        'GPS Quality Issues Found': '发现 GPS 质量问题',
        'files have GPS quality issues:': '个文件存在 GPS 质量问题:',
        'All files have good GPS quality:': '所有文件 GPS 质量良好:',
        'Render All': '全部渲染',
        'File': '文件',
        'GPS Quality': 'GPS 质量',
        'Files with poor GPS may show incorrect speed, position, and map data.': 'GPS 质量较差的文件可能显示错误的速度、位置和地图数据。',
        'Excellent': '优秀',
        'Good': '良好',
        'Poor': '较差',
        'No Signal': '无信号',
        'External GPX': '外部 GPX',
        'Skipped': '已跳过',
        'Not Found': '未找到',
        'Error': '错误',
        'Unknown': '未知',
        'Low GPS Quality Warning': 'GPS 质量较低警告',
        'The overlay may show:': '叠加层可能显示:',
        'Incorrect speed and position data': '错误的速度和位置数据',
        'Jumpy or missing values': '数值跳变或缺失',
        'Map not tracking correctly': '地图跟踪不正确',
        'Render Anyway': '仍然渲染',
        'This video has poor GPS signal:': '该视频 GPS 信号较差:',
        'GPS signal was not acquired during recording': '录制过程中未获取 GPS 信号',
        'DOP: 99.99 (invalid)': 'DOP: 99.99（无效）',
        'Only GPS points are usable': '可用 GPS 点比例',
        'Average DOP': '平均 DOP',
        'recommended < 10': '建议 < 10',
        'GPS lock rate': 'GPS 锁定率',
        'Starting...': '正在启动...',
        'Analyzing...': '正在分析...',
        'All jobs finished': '所有任务已完成',
        'Starting next job...': '正在启动下一个任务...',
        'frames/s': '帧/秒',
        'AMap JS API': '高德 JS API',
        'AMap requires a validated key and security JS code.': '高德地图需要先验证 Key 和安全密钥。',
        'AMap key and security JS code are required.': '请输入高德 Key 和安全密钥。',
        'AMap credentials are not configured.': '尚未配置高德 Key 和安全密钥。',
        'AMap settings saved': '高德配置已保存',
        'AMap validation succeeded': '高德验证成功',
        'AMap settings cleared': '高德配置已清除',
        'Validated': '已验证',
        'Validation Required': '需要验证',
        'Setup Required': '需要配置',
        'Not configured': '未配置',
        'Saved key fingerprint': '已保存 Key 指纹',
        'Enter AMap Web JSAPI key and security JS code.': '请输入高德 Web JSAPI Key 和安全密钥。',
        'Web JSAPI key': 'Web JSAPI Key',
        'Security JS code': '安全密钥',
        'Validate': '验证',
    };
    const en = {};
    const reverseZh = Object.fromEntries(Object.entries(zh).map(([k, v]) => [v, k]));

    function normalize(language) {
        return SUPPORTED.has(language) ? language : DEFAULT_LANGUAGE;
    }

    function getLanguage() {
        return normalize(localStorage.getItem(STORAGE_KEY) || DEFAULT_LANGUAGE);
    }

    function setLanguage(language) {
        const normalized = normalize(language);
        localStorage.setItem(STORAGE_KEY, normalized);
        document.documentElement.lang = normalized === 'zh-CN' ? 'zh-CN' : 'en';
        document.dispatchEvent(new CustomEvent('language:changed', { detail: { language: normalized } }));
        return normalized;
    }

    function t(text) {
        const language = getLanguage();
        if (language === 'zh-CN') return zh[text] || text;
        return reverseZh[text] || en[text] || text;
    }

    function translateTextNode(node, language) {
        const raw = node.nodeValue;
        const trimmed = raw.trim();
        if (!trimmed) return;
        const translated = language === 'zh-CN' ? (zh[trimmed] || trimmed) : (reverseZh[trimmed] || trimmed);
        if (translated !== trimmed) {
            node.nodeValue = raw.replace(trimmed, translated);
        }
    }

    function translateElementAttributes(el, language) {
        for (const attr of ['title', 'placeholder', 'aria-label']) {
            const value = el.getAttribute(attr);
            if (!value) continue;
            const translated = language === 'zh-CN' ? (zh[value] || value) : (reverseZh[value] || value);
            if (translated !== value) el.setAttribute(attr, translated);
        }
    }

    function apply(root = document.body) {
        const language = getLanguage();
        document.documentElement.lang = language === 'zh-CN' ? 'zh-CN' : 'en';

        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                const parent = node.parentElement;
                if (!parent) return NodeFilter.FILTER_REJECT;
                if (['SCRIPT', 'STYLE', 'PRE', 'CODE', 'TEXTAREA'].includes(parent.tagName)) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        const textNodes = [];
        while (walker.nextNode()) textNodes.push(walker.currentNode);
        textNodes.forEach(node => translateTextNode(node, language));
        root.querySelectorAll?.('[title], [placeholder], [aria-label]').forEach(el => translateElementAttributes(el, language));
    }

    window.i18n = { getLanguage, setLanguage, t, apply, normalize };
})();
