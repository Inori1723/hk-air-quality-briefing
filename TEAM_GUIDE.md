# Groupby 组员开发与使用手册

> 本手册配套 `Groupby_StarterPack.zip` 使用，帮 **任务 B / 任务 C / 任务 D** 在 **5 分钟内跑通环境、连上数据库并开始编写各自模块**。  
> 详细字段与接口命名以同目录下的 [SCHEMA_AND_INTERFACE.md](SCHEMA_AND_INTERFACE.md) 为准。

---

## 一、第一步：解压与环境跑通（本地 / Google Colab 通用）

### 1.1 解压与目录说明
请将 `Groupby_StarterPack.zip` **完整解压**，保持内部目录层级不变（不要把文件打散单独拿出来，否则相对路径会失效）：

```text
Groupby_StarterPack/
├── TEAM_GUIDE.md                 # 本使用手册
├── SCHEMA_AND_INTERFACE.md       # 8 张表结构、口径与模块接口契约
├── data/
│   ├── db/air_quality.db         # 已灌满 2025 全年数据的 SQLite 数据库
│   └── raw/geo_population/       # 18 区 GeoJSON 边界与 18 站官方坐标
├── scripts/
│   └── plot_proposal_example.py  # Matplotlib 图表样式参考脚本
└── src/
    ├── __init__.py
    ├── schema.py                 # 统一数据库连接工具 get_connection()
    ├── etl_aqhi.py               # (参考用) AQHI 清洗入库脚本
    └── etl_extra.py              # (参考用) 污染物/气象/坐标/人口入库脚本
```

### 1.2 先备份一份数据库！
在做任何增删改（CRUD）或写表测试之前，建议先复制一份：
`data/db/air_quality.db` → `data/db/air_quality_backup.db`，测试脏了随时覆盖还原。

### 1.3 两种开发环境跑通方法

#### 方式 A：本地电脑（VS Code / PyCharm / Jupyter Notebook，推荐）
1. 建议 **Python 3.10+**。
2. 依赖库需求：
   - **任务 B / 任务 C**：几乎只用到 Python 内置标准库（`sqlite3`、`json`、`pathlib`、`datetime`），**无需额外装包**就能跑！
   - **任务 D**：需要安装可视化库：
     ```bash
     pip install matplotlib folium pandas
     ```
3. 在 `Groupby_StarterPack` 根目录下新建测试脚本或 Notebook，运行下面代码确认连库成功：

```python
from src.schema import get_connection

with get_connection() as conn:
    aqhi_cnt = conn.execute("SELECT COUNT(*) FROM hourly_aqhi").fetchone()[0]
    pol_cnt = conn.execute("SELECT COUNT(*) FROM hourly_pollutants").fetchone()[0]
    w_cnt = conn.execute("SELECT COUNT(*) FROM daily_weather").fetchone()[0]
    print(f"连接成功 -> AQHI: {aqhi_cnt} 行 | 污染物: {pol_cnt} 行 | 气象: {w_cnt} 天")
```
正常输出应为：`AQHI: 157680 行 | 污染物: 157680 行 | 气象: 365 天`。

#### 方式 B：Google Colab
1. 把整个 `Groupby_StarterPack` 文件夹上传到 Google Drive 根目录（如 `MyDrive/Groupby_StarterPack`）。
2. 在 Colab 第一个代码格运行：
```python
from google.colab import drive
import sys

drive.mount('/content/drive')
PROJECT_DIR = '/content/drive/MyDrive/Groupby_StarterPack'
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.schema import get_connection
with get_connection() as conn:
    print(conn.execute("SELECT name, station_type FROM stations LIMIT 5").fetchall())
```
*(提示：`get_connection()` 返回的每一行都是 `sqlite3.Row`，既可以用 `row[0]` 下标取，也可以直接用列名 `row["name"]` 或 `dict(row)` 转字典。)*

---

## 二、写代码前必看的 4 条数据口径红线

1. **永远使用 `get_connection()`**：它会自动开启 `PRAGMA foreign_keys = ON`（保证外键检查生效）和 `sqlite3.Row`。
2. **`10+`（Serious）绝不能当数字 11 平均**：
   - 库里 `10+` 存为 `raw_value = '10+'`、`numeric_value = NULL`、`sort_rank = 11`、`category = 'Serious'`。
   - **找最大值 / 峰值 / 排序**请用 `sort_rank`（查出 `11` 时展示为 `'10+'`）；**算均值**只能用 `numeric_value`（SQLite `AVG(numeric_value)` 会自动忽略 `NULL`）。
3. **分母与缺失/替代统计口径**：
   - **有效小时数**：`SUM(CASE WHEN is_missing = 0 THEN 1 ELSE 0 END)`
   - **有效替代小时数（含 `*`）**：`SUM(CASE WHEN is_missing = 0 AND is_substitute = 1 THEN 1 ELSE 0 END)`
   - **缺失小时数**：`SUM(is_missing)`（包含空白、`-` 和 `-*`）
   - 算百分比请务必用 `ROUND(100.0 * count / NULLIF(valid_hours, 0), 1)` 防止某天全天缺失导致除零报错。
4. **2025-03-22 计算方法更新**：当报告时间范围跨过或包含 `2025-03-22` 附近对比时，模板层须附带 EPD 算法变更说明，不能把跨期指数变化直接等同于污染物浓度变化。

---

## 三、分任务实战指引（该写什么、怎么自测）

### 任务 B：数据库 & SQL 架构师（交付 `src/crud.py`、`src/queries.py`、ER 图）

#### 1. `src/queries.py` 怎么写
* 在 `src/queries.py` 中维护全部 **9 条 SQL**（对应计划书 8 个模板 + 1 条报告历史统计查询），并提供：
  1. `seed_saved_queries(db_path=...)`：把 SQL 文本、参数名、说明写入 `saved_queries` 表（可用 `INSERT ... ON CONFLICT(query_code) DO UPDATE SET ...` 方便反复更新）。
  2. `run_saved_query(query_code, params)`：从 `saved_queries` 查出 `sql_text` 并带参数执行，返回 `[dict(row) for row in rows]`。
* **SQL 查询必须体现**：`JOIN`、`LEFT JOIN`、子查询（Subquery）、聚合函数（`COUNT/MIN/MAX/SUM/AVG`）、`CASE`、`GROUP_CONCAT`、`GROUP BY`、`IN`。
* **最小参考示例（`Q01_daily_briefing` 核心思路，可直接运行）**：
```sql
SELECT
    s.name AS station_name,
    s.station_type,
    d.english_name AS district_name,
    h.obs_date,
    COUNT(CASE WHEN h.is_missing = 0 THEN 1 END) AS valid_hours,
    SUM(h.is_missing) AS missing_hours,
    SUM(CASE WHEN h.is_missing = 0 AND h.is_substitute = 1 THEN 1 ELSE 0 END) AS substitute_hours,
    MIN(CASE WHEN h.is_missing = 0 THEN h.sort_rank END) AS min_rank,
    MAX(h.sort_rank) AS max_rank,
    (
        SELECT GROUP_CONCAT(printf('%02d:00', h2.obs_hour), ', ')
        FROM hourly_aqhi h2
        WHERE h2.station_id = s.station_id
          AND h2.obs_date = h.obs_date
          AND h2.sort_rank = (
              SELECT MAX(h3.sort_rank)
              FROM hourly_aqhi h3
              WHERE h3.station_id = s.station_id AND h3.obs_date = h.obs_date
          )
    ) AS peak_hours,
    ROUND(AVG(p.pm25), 2) AS avg_pm25,
    COUNT(p.pm25) AS valid_pm25_hours,
    w.mean_temp_c,
    w.mean_rh_pct,
    w.rainfall_mm
FROM hourly_aqhi h
JOIN stations s ON s.station_id = h.station_id
JOIN districts d ON d.district_id = s.district_id
LEFT JOIN hourly_pollutants p
       ON p.station_id = h.station_id AND p.obs_date = h.obs_date AND p.obs_hour = h.obs_hour
LEFT JOIN daily_weather w ON w.obs_date = h.obs_date
WHERE s.name = :station_name AND h.obs_date = :obs_date
GROUP BY s.station_id, h.obs_date;
```
* **特别提醒**：写 `Q05_district_map` 时，请从 `districts d LEFT JOIN stations s ON s.district_id = d.district_id AND s.station_type = 'General' LEFT JOIN hourly_aqhi h ...` 出发，这样没有一般站的 4 个区（`Wan Chai`、`Yau Tsim Mong`、`Kowloon City`、`Wong Tai Sin`）才会保留为 `NULL` 而不是被过滤掉。

#### 2. `src/crud.py` 怎么写
* 为 **全部 8 张表** 写参数化 SQL 的 `create_*`、`get_*`、`update_*`、`delete_*`（禁止字符串拼接防 SQL 注入）。
* **外键依赖检查（评分关键点）**：因为建表时设置了 `ON DELETE RESTRICT`，删除父表（如 `districts`、`stations`、`saved_queries`、`report_templates`）前，函数里应先检查子表引用数（或提供明确的错误提示 / 可选级联清理逻辑），并在最终 Notebook 里为**每张表准备一段简短的增删改查演示**。

---

### 任务 C：模板引擎 & 英文报告主笔（交付 `src/templates.py`、600–800 词报告）

#### 1. `src/templates.py` 怎么写
* 在 `seed_report_templates()` 中把 **8 套英文简报模板** 写入 `report_templates` 表：
  - `Daily station briefing`、`Daily category breakdown`、`Comparison of two stations`、`Weather and pollution summary`、`District map report`、`Monthly station summary`、`High risk episode bulletin`、`Air quality news flash`。
  - 每套模板都要同时存好 `text_template`、`markdown_template`、`html_template` 三份模板内容，以及 `required_variables`（JSON 列表）。
* **共享渲染函数 `generate_report(template_name, params, save=True)` 标准流程**：
  1. 根据 `template_name` 查出 `report_templates` 及其关联的 `saved_queries.query_code`。
  2. 执行查询取数；先检查是否**无有效记录**（例如无高风险时段或日期无数据）→ 返回明确的英文说明（如 `"No hours reached AQHI 7 or above..."`），不报 KeyError、不伪造 0。
  3. 校验所有 `required_variables` 是否存在，若字段为 `NULL`（如某天缺失风速或某项污染物），显示为 `"N/A (not available)"`。
  4. 判断时间范围是否跨越 `2025-03-22`，若是则自动拼接 EPD 口径变更提示。
  5. 若 `max_rank == 11`，确保文本中展示为 `10+ (Serious)`，而不是数字 `11`。
  6. 同步填充生成 `text_output`、`markdown_output`、`html_output`，并在 `save=True` 时 `INSERT` 进 `generated_reports` 表返回 `report_id`。

#### 2. 600–800 词英文报告要点
* 必须覆盖课程大纲规定的 7 个部分：Problem analysis / Topic / Solutions / Approach & methods / ER Schema / Table structure & queries / Results & findings。
* **词数卡死在 600–800 words**（不含代码附录或按 Word 统计），最终交组长前过一遍查重。

---

### 任务 D：可视化、前端发布 & 视频合成（交付 `src/viz.py`、`src/site_export.py`、PPT/MP4）

#### 1. Matplotlib 图表（`src/viz.py`）
* 先运行并参考 `scripts/plot_proposal_example.py`，把硬编码逻辑改造成可传任意 `(station_name, obs_date)` 从 `air_quality.db` 实时查询画图的函数：
  - `plot_hourly_aqhi(station_name, obs_date, out_path)`：逐小时折线 + 风险色带 + 最高值标注（注意遇到 `10+` 时纵轴把 `sort_rank=11` 标签写为 `'10+'`，缺失小时断开不连零）。
  - `plot_category_distribution(station_name, obs_date, out_path)`：5 个健康风险等级小时数与占比横向柱状图。
  - 额外可加：两站对比柱状图、月度趋势图等用于丰富网站与报告。

#### 2. Folium 18 区交互地图（`src/viz.py`）
* 边界文件：`data/raw/geo_population/cydalytics_hkg_adm1.geojson`
  - **关键对接字段**：GeoJSON 中每个区的属性 `feature["properties"]["name_1"]` **与数据库 `districts.english_name` 100% 完全一致**，无需额外手写转换表！
* **作图规则（严格对应计划书）**：
  - 仅使用每个区内的**一般监测站（`station_type = 'General'`）**日最大 `sort_rank` 给对应区的多边形上色；
  - 没有一般站的 4 个区（`Wan Chai`、`Yau Tsim Mong`、`Kowloon City`、`Wong Tai Sin`）**保持灰色不插值**；
  - **路边站（`Causeway Bay`、`Central`、`Mong Kok`）** 放到单独的 `folium.FeatureGroup` 图层，用不同颜色的 `CircleMarker` 标在精确经纬度（`stations.latitude`, `stations.longitude`）上，点击弹出 `Popup` 显示当天最大 AQHI、站点类型与所属区信息。

#### 3. GitHub Pages 静态导出（`src/site_export.py`）
* 从 `generated_reports` 读取选定简报，导出为独立 `.html` / `.md` 文件到 `docs/`，连同 `viz.py` 产出的 PNG 图表与 Folium 地图 `.html`，再由 Python 自动生成响应式 `docs/index.html`（手机和电脑都能正常排版点击），推送到 GitHub 开启 Pages 即可。
* **注意**：网站里不要写前端 JS 去查 SQLite，也不要用 Chart.js/ECharts 重画图表——全部图表、地图和简报 HTML 均由 Python 导出静态文件！

---

## 四、联调与提交代码注意事项

1. **不要改动共享底库结构**：不要修改 `src/schema.py` 的表名/列名，也不要把你们测试写的垃圾记录留在最后发回的 `air_quality.db` 里（最后交回你写的 `.py` 脚本和模板/查询初始化函数即可，组长会用 `etl` + 大家的 `seed_*` 从零干净生成终版数据库）。
2. **文件交付清单**：
   - 任务 B 交：`src/crud.py`、`src/queries.py`、ER Schema 高清图
   - 任务 C 交：`src/templates.py`、8 类样例输出确认、600–800 词英文报告初/终稿
   - 任务 D 交：`src/viz.py`、`src/site_export.py`、`docs/` 静态站点、PPT 母版与合成后的 MP4 视频
3. **视频录制自检（每人必看）**：
   - 全组总时长 **≤ 10 分钟**（每人约 2–2.5 分钟）；
   - **必须露脸**（摄像头小窗放角落即可）；
   - **PPT 页面或视频画面中必须标出当前讲解人姓名**。
