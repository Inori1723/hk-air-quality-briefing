# 香港空气质量简报系统使用手册（Hong Kong Air Quality Briefing System · Groupby）

> **课程**：HKBU AIDM7360 — Big Data Management and Analytics  
> **版本**：汇总定稿版（对应 `main.ipynb`、`air_quality.db` 全 8 表及 `docs/` 静态站点）

---

## 1. 系统概述与团队模块分工

本系统基于 **Python + SQLite** 实现 2025 年香港空气质量数据的自动入库、查询统计、多格式简报渲染、可视化交互与静态网页发布：

| 分工 | 负责人 | 职责定位 | 核心文件与交付模块 |
| :--- | :--- | :--- | :--- |
| **任务 A（组长）** | 冯俊杰 | 数据工程与项目总集成 | `src/schema.py`、`src/etl_aqhi.py`、`src/etl_extra.py`、`src/etl.py`、`scripts/seed_project_db.py`、`main.ipynb` |
| **任务 B** | 黄郑颖 | 数据库与 SQL 架构 | `src/crud.py`、`src/queries.py`、`src/task_b_demo.ipynb`、`Groupby_Task_B_ER.pptx` |
| **任务 C** | 陈涵词 | 模板引擎与多格式渲染 | `src/templates.py`、`src/report_templates/`（`t1`–`t8` 八套模板定义） |
| **任务 D** | 侯杰宇 | 图表、地图、交互 UI 与静态发布 | `src/viz.py`、`src/task_d_integration.py`、`src/site_export.py`、`task_d_demo.ipynb`、`docs/` |

**数据库规模（`data/db/air_quality.db`）**：
- 基础事实与维度表（5 张）：`districts`（18 区）、`stations`（18 站：15 一般站 + 3 路边站）、`hourly_aqhi`（157,680 行）、`hourly_pollutants`（157,680 行）、`daily_weather`（365 天）。
- 查询与报告表（3 张）：`saved_queries`（9 条核心 SQL）、`report_templates`（8 套模板）、`generated_reports`（8 份预置样例简报）。

---

## 2. 运行环境准备

### 2.1 本地电脑（Windows / macOS / Linux，建议 Python 3.10+）

> **轻量说明**：若仅运行建库、ETL、CRUD、SQL 查询或纯文本/Markdown/HTML 简报生成（`src.schema`、`src.etl*`、`src.crud`、`src.queries`、`src.templates`），**仅依赖 Python 标准库，无需安装第三方包**；运行图表、Folium 地图、Notebook 与 `pytest` 测试需安装 `requirements.txt`。

在项目根目录（`AIDM7360_group_project/`）打开终端执行：

```powershell
# 1. 创建并激活虚拟环境（Windows PowerShell）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 安装完整依赖
pip install -r requirements.txt
```

### 2.2 Google Colab

1. 将完整的项目根目录文件夹（包含 `data/`、`src/`、`scripts/`、`main.ipynb`、`requirements.txt`）上传至 Google Drive（例如 `MyDrive/AIDM7360_group_project`）。
2. 在 Colab 新建或打开 `main.ipynb`，先挂载 Drive 并切换至项目根目录：
   ```python
   from google.colab import drive
   drive.mount("/content/drive")
   %cd /content/drive/MyDrive/AIDM7360_group_project
   %pip install -r requirements.txt
   ```
3. 如 Notebook 未在根目录打开，可先设置环境变量再运行代码单元：
   ```python
   import os
   os.environ["AQHI_PROJECT_ROOT"] = "/content/drive/MyDrive/AIDM7360_group_project"
   ```

---

## 3. 五大核心操作流程

### 3.1 运行统一总控笔记本（`main.ipynb`）

1. 在本地 JupyterLab / Notebook / VS Code（内核选择 `.venv`）或 Google Colab 中打开根目录下的 `main.ipynb`。
2. 依次运行全部代码单元即可完成以下演示：
   - **环境与数据质检**：校验 8 张表行数与 AQHI 有效/缺测/替代/`10+` 口径统计。
   - **9 条 SQL 查询演示（`Q01`–`Q09`）**：展示日常简报、风险分布、双站对比、气象关联、18 区地图、月度汇总、高风险预警、全港快讯与报告历史。
   - **8 表参数化 CRUD 与外键保护**：在临时快照库完成全 8 表增删改查回环，并演示删除被引用的父模板时触发 `ReferencedRowError`。
   - **8 套共享模板渲染与边界处理**：输出 Plain Text / Markdown / HTML 三格式简报，并验证 `10+`、零高风险时段与无数据日期（不落库、不伪造 0）。
   - **交互式探索器**：通过下拉框选择站点、对比站、日期（覆盖 2025 全年 365 天）、月份或起止区间，点击按钮实时生成简报、4 张 Matplotlib 统计图与 Folium 18 区交互地图。
   - **静态站点导出与校验**：在临时目录执行站点导出并校验所有相对链接无误。
3. **Widget 控件不可用时的回退方式**：若运行环境未启用 `ipywidgets`（或设置 `AQHI_DISABLE_WIDGETS=1`），直接修改 `interactive_inputs = dict(...)` 参数单元中的 `template`、`station`、`other`、`day`、`month`、`start`、`end` 后重跑该单元即可。

> **源库安全说明**：`main.ipynb` 中的所有 CRUD 与写库演示均在 `TemporaryDirectory` 自动备份的临时 SQLite 快照（`demo_db`）中执行，**不会修改权威数据库 `data/db/air_quality.db`**。

---

### 3.2 执行保存查询与全表 CRUD（Python API）

#### 调用 9 条保存查询（`src/queries.py`）

```python
from src.queries import seed_saved_queries, run_saved_query

# 如需确保 saved_queries 已注册（幂等，保留已有 query_id）
seed_saved_queries()

# 示例 1：单站单日简报（Q01）
rows = run_saved_query(
    "Q01_daily_briefing",
    {"station_name": "Central/Western", "obs_date": "2025-04-01"},
)

# 示例 2：天气与污染物区间联查（Q04）
range_rows = run_saved_query(
    "Q04_weather_pollution",
    {"station_name": "Central/Western", "start_date": "2025-03-21", "end_date": "2025-03-23"},
)

# 示例 3：已生成报告历史统计（Q09）
history_rows = run_saved_query("Q09_report_history", {})
```

**9 条查询代码与必填参数速查**：

| `query_code` | 必填参数（`params` 字典键） | 用途说明 |
| :--- | :--- | :--- |
| `Q01_daily_briefing` | `station_name`, `obs_date` | 单站单日 AQHI 范围、峰值时段、污染物均值与日气象 |
| `Q02_category_breakdown` | `station_name`, `obs_date` | 单站单日 5 个健康风险等级小时数及有效占比 |
| `Q03_station_comparison` | `station_a`, `station_b`, `obs_date` | 同日双站对比（区分 General 与 Roadside） |
| `Q04_weather_pollution` | `station_name`, `start_date`, `end_date` | 区间逐日 AQHI、6 项污染物样本量及 HKO 气象背景 |
| `Q05_district_map` | `obs_date` | 18 区一般站日峰值行 + 3 个路边站独立行（含经纬度与人口） |
| `Q06_monthly_summary` | `station_name`, `month`（`YYYY-MM`） | 单站月度覆盖率、风险分布、均值/峰值与污染物统计 |
| `Q07_high_risk_bulletin` | `station_name`, `start_date`, `end_date` | 区间内出现 AQHI ≥ 7 的日期与具体高风险钟点 |
| `Q08_news_flash` | `obs_date` | 全港 15 个一般站日最高 AQHI、达峰站点与时段快讯 |
| `Q09_report_history` | `{}`（无参数） | 按模板与创建月份统计 `generated_reports` 数量 |

#### 全 8 张表参数化 CRUD（`src/crud.py`）

每张表均提供 `create_*`、`get_*`、`update_*`、`delete_*`（全部使用参数化 SQL 防止注入）：
- 对应表名：`district`、`station`、`hourly_aqhi`、`hourly_pollutant`、`daily_weather`、`saved_query`、`report_template`、`generated_report`。
- **联动与约束提示**：
  - 更新 `hourly_aqhi` 时必须通过 `raw_value`（如 `"4*"` 或 `"10+"`）更新，函数会自动同步推导 `numeric_value`、`sort_rank`、`category`、`is_substitute` 与 `is_missing`。
  - 删除被子表引用的父表记录（如已有生成报告的 `report_templates`）会抛出 `crud.ReferencedRowError`，须先删除子表记录。

---

### 3.3 生成、保存与导出三格式英文简报（`src/templates.py`）

```python
from src.templates import generate_report, export_report_files

# 1. 仅预览（不写库）：返回 dict，包含 formal / report_id / text_output / markdown_output / html_output
preview = generate_report(
    "Weather and Pollution Summary",
    {"station_name": "Central/Western", "start_date": "2025-03-21", "end_date": "2025-03-23"},
    save=False,
)
print(preview["text_output"])

# 2. 生成并写入 generated_reports 表（返回整数 report_id；无有效数据时返回 formal=False 且绝不落库）
report_id = generate_report(
    "Daily Station Briefing",
    {"station_name": "Central/Western", "obs_date": "2025-04-01"},
    save=True,
)

# 3. 从数据库读取并导出为 .txt / .md / .html 文件
if isinstance(report_id, int):
    paths = export_report_files(report_id, out_dir="exported_reports")
    print(paths)
```

8 套标准模板名称（`TEMPLATE_NAMES`）：
`Daily Station Briefing`、`Daily Category Breakdown`、`Comparison of Two Stations`、`Weather and Pollution Summary`、`District Map Report`、`Monthly Station Summary`、`High Risk Episode Bulletin`、`Air Quality News Flash`。

---

### 3.4 从原始数据一键重建数据库与刷新样例报告

当原始 CSV/XML/GeoJSON 更新，或模板文案修改后需要重置数据库时，在项目根目录执行：

```powershell
# 1. 从 data/raw/ 从零重建 5 张基础表并写入 saved_queries 与 report_templates
python -m src.etl

# 2. 幂等写入（或 --refresh 强制刷新）8 份默认样例报告到 generated_reports
python scripts/seed_project_db.py --refresh
```

---

### 3.5 重新生成静态站点（`docs/`）与发布 GitHub Pages

```powershell
# 1. 导出响应式主页、8 份 HTML/MD 简报、8 张 300 dpi 图表与 2 份 Folium 地图到 docs/
python -m src.site_export

# 2. 启动本地预览服务器（浏览器访问 http://127.0.0.1:8000/）
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

- 如需定制首页展示的示例日期，可调用 `export_static_site(demo_cases=[{"station_name": "Central/Western", "station_b": "Central", "obs_date": "2025-07-16"}])`；导出器会自动清理旧编号冗余资产并保留无关文件。
- **GitHub Pages 发布**：将包含 `docs/.nojekyll` 的完整 `docs/` 目录提交并推送到 GitHub 仓库后，在仓库 **Settings → Pages → Build and deployment** 中选择 **Deploy from a branch**，分支选目标分支、目录选 **`/docs`** 保存即可（详见 [GITHUB_PAGES_PUBLISH.md](GITHUB_PAGES_PUBLISH.md)）。
- **注意**：Folium 交互地图需要浏览器联网加载 Leaflet 脚本与 OpenStreetMap 底图瓦片。

---

## 4. 数据口径与边界处理规则速查

1. **`10+`（Serious）处理**：
   - 数据库中存为 `raw_value='10+'`、`numeric_value=NULL`、`sort_rank=11`、`category='Serious'`。
   - 最大值比较与排序统一使用 `sort_rank`（输出为 `'10+'` 或 `'10+ (Serious)'`）；计算均值仅允许使用 `AVG(numeric_value)`，绝不将 `11` 计入均值。
2. **缺失与替代记录**：
   - 空白、`-` 与 `-*` 均为缺失（`is_missing = 1`，不计为 0）；带 `*` 的数值记录保留 `is_substitute = 1, is_missing = 0`。
   - 百分比分母统一为有效小时数 `valid_hours`，并用 `NULLIF(valid_hours, 0)` 防止全天缺测除零；逐小时折线图遇到缺测小时会断开留空，不连向 0。
3. **6 项污染物及单位**：
   - `PM2.5`、`PM10`、`O3`、`NO2`、`SO2` 单位为 `ug/m3`，`CO` 单位为 `10 ug/m3`（部分一般站未测 `CO`，缺失时展示 `N/A (not available)` 并附有效测量小时数）。
4. **2025 年 3 月 22 日 EPD 算法更新**：
   - 报告或月度图表若跨越 `2025-03-22`，系统会自动附加 EPD 口径变更提示；其中 `Weather and Pollution Summary` 与 `Monthly Station Summary` 额外输出 `Pre-22 Mar` 与 `From 22 Mar` 两段 AQHI 极值/均值对照，月度折线图亦会绘制 22 日虚线标记。
5. **18 区地图与气象背景说明**：
   - 18 区填色仅使用区内的**一般站（General）**日最高 AQHI；无一般站的 4 个区（`Kowloon City`、`Wan Chai`、`Wong Tai Sin`、`Yau Tsim Mong`）保持浅灰不插值，悬浮 Tooltip 仍显示全港 18 区的 C&SD 2025 年中陆上人口与陆地面积；3 个路边站（`Causeway Bay`、`Central`、`Mong Kok`）位于可切换的独立图层。
   - HKO 日气象仅作同日背景上下文参考，不推导与小时 AQHI 峰值的因果关系。

---

## 5. 自动化测试与常见问题排查

### 运行全套回归测试

在项目根目录执行（确保关闭占用数据库文件的外部软件）：

```powershell
python -m pytest -v tests/test_task_d.py tests/test_integration.py
```

测试涵盖：基础库覆盖率校验、全库 ETL 从零重建及连接关闭验证、8 表 CRUD 与外键拦截、8 套模板三格式与边界/HTML 转义测试、图表 300 dpi 与 NaN 断线检查、Folium 18 区（含无一般站区人口 Tooltip）及路边站图层检验、`docs/` 相对链接校验，以及 `task_d_demo.ipynb` 与 `main.ipynb` 在 Widgets 启用与参数回退双模式下的内核实际执行。

### 常见问题排查

| 现象 | 原因 | 解决方法 |
| :--- | :--- | :--- |
| 报 `Locate the project root...` | 未从项目根目录启动 Python / Notebook | 切换到 `AIDM7360_group_project/` 目录，或设置环境变量 `AQHI_PROJECT_ROOT` 指向根目录 |
| Notebook 控件按钮未显示 | 环境未启用 `ipywidgets` 渲染 | 直接修改参数单元里的 `interactive_inputs` 字典并运行该单元 |
| Windows 报 Matplotlib 缓存目录权限警告 | 默认用户配置目录不可写 | 提前设置 `set MPLCONFIGDIR=.matplotlib`（或在代码里指定可写目录） |
| 地图空白但表格/报告正常 | 浏览器处于离线状态 | 确保联网以加载 Leaflet JS 及 OpenStreetMap 地图底图 |
| 提交压缩包体积过大 | 把虚拟环境或缓存一并打入 zip | 打包最终作业时**务必排除** `.venv/`、`.python_dependencies/`、`__pycache__/`、`.pytest_cache/`、`.ipynb_checkpoints/` 与历史备份包 |
