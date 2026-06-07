# gpstitch-mod

`gpstitch-mod` 是基于 GPStitch 的私人修改版，用于在 Windows 环境中批量制作带 GPS 轨迹、速度、地图和 DJI 相关信息的视频叠加层。

本项目仍使用原来的 Python 包名和命令入口：

- Python 包名：`gpstitch`
- Web 启动命令：`gpstitch`
- 渲染包装命令：`gpstitch-dashboard`

## 项目用途

这个修改版主要面向以下场景：

- 多个视频目录批量渲染。
- 一个 GPX/FIT 轨迹目录匹配多个视频目录。
- 一个共享 GPX 应用于多段视频，并自动计算每段视频的里程偏移。
- DJI 视频文件名时间、视频元数据时间、GPX 时间轴之间的稳定对齐。
- Windows 中文路径、H 盘/NAS 路径和 ffprobe 输出兼容。
- AMap 地图样式预览和最终视频渲染。
- 后台任务队列、并发渲染、失败重试和批量取消。

## 主要修改内容

### 任务管理

- 新增独立任务管理页面/模块，用于统一查看所有渲染任务。
- 支持渲染并发数配置，当前最多支持 3 个任务同时运行。
- 支持选择任务、全选任务、批量取消、批量重试失败任务。
- 支持清理已结束任务。
- 支持失败任务手动重试，并在手动重试时重置自动重试次数。
- 支持自动重试临时失败任务。
- 将“渲染完成后关机”从快速模式和批量渲染弹窗迁移到任务管理模块。
- 新的关机开关语义为：打开后，所有排队/运行中的渲染任务完成时执行关机。
- 任务管理状态中显示等待中、运行中、已完成、失败、已取消数量。

### 批量渲染

- 修复一次选择多个视频目录后重复弹出选择窗口的问题。
- 修复一次选择多个 GPX 目录后重复弹出选择窗口的问题。
- 支持选择多个视频目录并递归收集视频。
- 支持选择 GPX/FIT 目录后，根据视频文件和轨迹文件自动匹配。
- 修复多个视频目录 + 包含对应轨迹的 GPX 目录时，错误提示“找不到匹配 GPS 轨迹”的问题。
- 保留共享 GPX 模式：一个 GPX 轨迹可应用到一个或多个视频。
- 批量任务创建后会立即填满可用并发槽位，不再只启动一个任务。
- 批量任务支持预检查输出文件冲突和 GPS 质量问题。

### 失败重试和任务恢复

- 渲染任务会持久化本地 session 文件快照，包括主视频和辅助 GPX/FIT/SRT 文件。
- 服务重启后，失败任务或排队任务可根据持久化文件快照恢复本地 session。
- 对较早创建、没有 session 快照的任务，尝试从历史命令日志中恢复视频和 GPX 路径。
- 修复失败任务批量重试时，只有最先进入并发槽位的任务能运行，其余排队任务被误判为 orphaned job 的问题。
- orphaned 清理现在会保留可恢复的本地任务，不再误杀仍可重试的 pending job。

### Windows 路径和 ffprobe JSON 兼容

- 修复 ffprobe 输出中 Windows 反斜杠路径导致的 `json.decoder.JSONDecodeError: Invalid \escape`。
- 兼容中文路径、H 盘路径和被 Windows 默认编码影响后的混合转义路径。
- gopro-overlay 的 `FFMPEGGoPro.find_recording()` 和相关 ffprobe JSON 解析会使用 GPStitch 的宽松 JSON loader。
- 元数据读取、旋转检测、timecode 提取等路径也统一走兼容解析。

### DJI 和 GPX 时间对齐

- DJI 文件名中的 `DJI_YYYYMMDDHHMMSS` 时间优先参与视频开始时间判断。
- 修复部分视频 `creation_time` 与真实录制时间冲突时的对齐问题。
- GPX local-as-UTC 时间轴偏移会传递到预览、时间同步和最终渲染包装脚本。
- 新增 wrapper 参数用于 GPX 时间偏移和共享 GPX 里程偏移。
- 渲染前会根据视频时间和 GPX 轨迹计算共享 GPX 的里程起点。

### AMap 地图渲染

- 支持 AMap JSAPI 地图用于预览和最终视频渲染。
- 支持普通、卫星、混合等地图样式。
- 针对不同地图组件区分底图/路网渲染逻辑。
- 支持地图瓦片/截图缓存和渲染前预热。
- 修复部分地图组件在最终视频中显示不一致的问题。

### UI 和本地文件选择

- 新增本地多目录选择接口。
- 批量渲染弹窗显示视频目录、GPS 目录、视频数量和匹配到的 GPS 数量。
- 任务管理 UI 增加复选框、全选、批量按钮和任务详情面板。
- 增加中文界面文案和部分英文文案。
- 快速模式和批量渲染中移除原来的单独关机开关，避免多个入口语义冲突。

### 测试和稳定性

- 增加批量渲染、任务管理、失败重试、并发队列、session 恢复、AMap、GPX 时间偏移、Windows JSON 解析等测试。
- API 测试隔离真实任务目录，避免测试任务写入用户的真实临时任务列表。
- 增加对运行中任务、排队任务、失败任务、批量取消和批量重试的覆盖。

## 安装和运行

### 前置要求

- Windows 10/11 或其他支持 Python 3.12+ 的系统。
- Python 3.12+
- FFmpeg 和 ffprobe，需要能在命令行中直接运行。
- 项目根目录 `.venv` 是默认虚拟环境。

### 使用本地虚拟环境

```powershell
cd E:\github\GPStitch
.\.venv\Scripts\python.exe -m uvicorn gpstitch.app:app --host 127.0.0.1 --port 8000
```

启动后访问：

```text
http://127.0.0.1:8000
```

### 命令行渲染

Web 界面生成的命令会通过 `gpstitch-dashboard` 包装脚本执行。包装脚本会先应用 GPStitch 运行时补丁，再调用原始 `gopro-dashboard.py`。

示例：

```powershell
.\.venv\Scripts\gpstitch-dashboard.exe video.mp4 output.mp4 --layout xml --layout-xml layout.xml
```

## 常用测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\services\test_job_manager.py -q
.\.venv\Scripts\python.exe -m pytest tests\api\test_render.py tests\api\test_batch_render.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\services\test_render_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\patches\test_patches.py -q
```

## 注意事项

- 修改后如果已有 GPStitch 服务在运行，需要重启服务，新补丁才会生效。
- 批量重试旧失败任务时，建议先确认任务详情中保存了原视频和 GPX/FIT 路径。
- 若 Windows 中文路径显示成乱码但实际路径存在，渲染链路会尽量按真实路径恢复和解析。
- 私有仓库名建议使用 `gpstitch-mod`，避免与上游 GPStitch 混淆。

## 许可证

本项目基于 GPStitch 修改，继续遵循原项目的 GPL-3.0-or-later 许可证。详见 [LICENSE](LICENSE)。
