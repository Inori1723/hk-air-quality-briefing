# Groupby 数据库结构与组员开发接口契约（Day 1 冻结版）

> 面向 **任务 A（ETL & 总集成）/ 任务 B（SQL & CRUD）/ 任务 C（模板 & 报告）/ 任务 D（图表 & 地图 & Pages）**  
> 当前数据库文件：`data/db/air_quality.db`（**已全部加载 5 张基础事实与维度表**：2025 全年 AQHI `157,680` 行、EPIC 污染物 `157,680` 行、HKO 日气象 `365` 天、18 区人口/面积、18 站官方精确坐标；仅 `saved_queries`、`report_templates`、`generated_reports` 待任务 B/C 填充）。

---

## 一、项目目录与模块分工约定

```text
AIDM7360_group_project/
├── data/
│   ├── raw/
│   │   ├── aqhi_2025/            # [已完成] 202501_Eng.csv ~ 202512_Eng.csv
│   │   ├── air_hourly.csv        # [已完成] EPIC 2025 小时污染物 (157,680 行)
│   │   ├── weather_2025/         # [已完成] HKO & 京士柏 2025 日气象 CSV / XML
│   │   └── geo_population/       # [已完成] cydalytics_hkg_adm1.geojson, had_district_boundary.geojson,
│   │                             #         epd_monitoring_stations.geojson, csd_table_110_02001_en.json
│   └── db/
│       └── air_quality.db        # 唯一权威 SQLite 数据库（5 张数据表已满载就绪）
├── src/
│   ├── __init__.py               # [已完成]
│   ├── schema.py                 # [已完成] 8 张表 DDL 与 get_connection() / init_db()
│   ├── etl_aqhi.py               # [已完成] 2025 AQHI + 18 区 + 18 站清洗入库
│   ├── etl_extra.py              # [已完成] 污染物、气象、官方坐标与 C&SD 人口面积补入脚本
│   ├── crud.py                   # [任务 B] 全 8 张表的参数化 Insert/Select/Update/Delete
│   ├── queries.py                # [任务 B] 8+1 条核心 SQL 定义、入库 saved_queries 及执行封装
│   ├── templates.py              # [任务 C] 8 套模板初始化、占位符校验与 Text/MD/HTML 渲染落库
│   ├── viz.py                    # [任务 D] Matplotlib 图表与 Folium 18 区交互地图生成
│   └── site_export.py            # [任务 D] 静态页面导出器（生成 docs/index.html 供 GitHub Pages）
├── docs/                         # [任务 D] GitHub Pages 发布目录（导出 HTML/MD/PNG/地图）
└── main.ipynb                    # [任务 A 牵头总装] 运行入口与全表 CRUD/简报/可视化演示
```

---

## 二、8 张表结构与关键口径（严禁随意改列名）

所有连接请使用 `from src.schema import get_connection`，默认已开启 `PRAGMA foreign_keys = ON`。

1. **`districts`**（18 个行政区，已含 C&SD 2025 年中陆上人口与面积）
   - `district_id` (PK), `district_code` (UNIQUE), `english_name` (UNIQUE), `region`, `population_2025` (已入库), `area_sqkm` (已入库), `population_ref_year` (`'2025 Mid-year (C&SD Table 110-02001)'`)
2. **`stations`**（18 个监测站，已含 CSDI 官方经纬度）
   - `station_id` (PK), `code` (UNIQUE), `name` (UNIQUE), `station_type` (`'General'` / `'Roadside'`), `district_id` (FK -> `districts`), `latitude` (已入库), `longitude` (已入库)
3. **`hourly_aqhi`**（2025 全年逐小时 AQHI，`157,680` 行）
   - `aqhi_id` (PK), `station_id` (FK), `obs_date` (`YYYY-MM-DD`), `obs_hour` (`1..24`), `raw_value`, `numeric_value` (`1..10` or `NULL`), `sort_rank` (`1..11` or `NULL`), `category` (`'Low'`/`'Moderate'`/`'High'`/`'Very high'`/`'Serious'`/`NULL`), `is_substitute` (`0/1`), `is_missing` (`0/1`)
   - 唯一键：`UNIQUE (station_id, obs_date, obs_hour)`
4. **`hourly_pollutants`**（2025 全年逐小时污染物，`157,680` 行）
   - `pollutant_id` (PK), `station_id` (FK), `obs_date`, `obs_hour`, `pm25`, `pm25_unit` (`'ug/m3'`), `pm10`, `pm10_unit` (`'ug/m3'`), `o3`, `o3_unit` (`'ug/m3'`), `no2`, `no2_unit` (`'ug/m3'`), `so2`, `so2_unit` (`'ug/m3'`), `co`, `co_unit` (`'10 ug/m3'`)
   - 唯一键：`UNIQUE (station_id, obs_date, obs_hour)`
5. **`daily_weather`**（2025 全年日气象，`365` 行）
   - `weather_id` (PK), `obs_date` (UNIQUE), `mean_temp_c`, `max_temp_c`, `min_temp_c`, `mean_rh_pct`, `rainfall_mm` (`Trace` 存为 `0.0` 并记于 `source_note`), `mean_wind_kmh` (京士柏 `KP`, 缺失为 `NULL`), `sunshine_hours` (京士柏 `KP`), `source_note`
6. **`saved_queries`**（任务 B 维护）
   - `query_id` (PK), `query_code` (UNIQUE), `name`, `sql_text`, `parameter_names`, `description`, `updated_at`
7. **`report_templates`**（任务 C 维护）
   - `template_id` (PK), `query_id` (FK -> `saved_queries`), `name` (UNIQUE), `scope`, `required_variables`, `text_template`, `markdown_template`, `html_template`, `version`, `updated_at`
8. **`generated_reports`**（任务 C 写入，任务 B 管理 CRUD，任务 D 导出）
   - `report_id` (PK), `template_id` (FK -> `report_templates`), `station_id` (FK -> `stations`, **允许 NULL**), `title`, `parameter_values`, `reporting_period`, `text_output`, `markdown_output`, `html_output`, `created_at`, `updated_at`

---

## 三、任务 B / C / D 必须统一的数据口径（已实测验证）

1. **`10+`（Serious）处理**：
   - `raw_value = '10+'`、`numeric_value = NULL`、`sort_rank = 11`、`category = 'Serious'`。
   - **最大值/排序请用 `sort_rank`（`MAX(sort_rank)`，输出时若 `sort_rank == 11` 显示为 `'10+'`）**；平均值统计（若有）只允许使用 `numeric_value`（SQLite `AVG(numeric_value)` 自动忽略 `NULL`），绝不能把 `11` 当真实数值算均值。
2. **缺失值与星号 `*` 替代值（含 `-*` 实测边界）**：
   - 2025 全年共 `157,347` 条有效小时记录、`333` 条缺失记录（`is_missing = 1`，含空白、`-` 以及 `155` 条带星号的缺失值 `-*`）、`3,886` 条含 `*` 记录（其中有效替代记录 `3,731` 条）、`47` 条 `10+` 记录。
   - 统计**有效小时数**：`SUM(CASE WHEN is_missing = 0 THEN 1 ELSE 0 END)`；
   - 统计**有效替代记录数**：`SUM(CASE WHEN is_missing = 0 AND is_substitute = 1 THEN 1 ELSE 0 END)`；
   - 统计**缺失记录数**：`SUM(is_missing)`；
   - 百分比分母统一用**有效小时数**，并做 `NULLIF(valid_hours, 0)` 防除零保护。
3. **2025 年 3 月 22 日算法更新提示**：
   - 当查询/报告的起止日期跨越 `2025-03-22`（或单日报告恰为该日期附近对比）时，任务 C 的渲染函数自动附带 EPD 计算口径调整注释。
4. **18 个站点与 18 个行政区标准对照表**（注意一般站仅覆盖 14 个区；`Wan Chai`、`Yau Tsim Mong`、`Kowloon City`、`Wong Tai Sin` 均无一般监测站，地图须留灰不插值）：

| `station_id` | `code` | `name`（CSV 标准名） | `station_type` | 所属区 `english_name` |
| :---: | :---: | :--- | :---: | :--- |
| 1 | `CW` | `Central/Western` | General | `Central and Western` |
| 2 | `SO` | `Southern` | General | `Southern` |
| 3 | `EN` | `Eastern` | General | `Eastern` |
| 4 | `KT` | `Kwun Tong` | General | `Kwun Tong` |
| 5 | `SSP` | `Sham Shui Po` | General | `Sham Shui Po` |
| 6 | `KC` | `Kwai Chung` | General | `Kwai Tsing` |
| 7 | `TW` | `Tsuen Wan` | General | `Tsuen Wan` |
| 8 | `TKO` | `Tseung Kwan O` | General | `Sai Kung` |
| 9 | `YL` | `Yuen Long` | General | `Yuen Long` |
| 10 | `TM` | `Tuen Mun` | General | `Tuen Mun` |
| 11 | `TC` | `Tung Chung` | General | `Islands` |
| 12 | `TP` | `Tai Po` | General | `Tai Po` |
| 13 | `ST` | `Sha Tin` | General | `Sha Tin` |
| 14 | `NO` | `North` | General | `North` |
| 15 | `MB` | `Tap Mun` | General | `Tai Po` |
| 16 | `CB` | `Causeway Bay` | Roadside | `Wan Chai` |
| 17 | `CL` | `Central` | Roadside | `Central and Western` |
| 18 | `MK` | `Mong Kok` | Roadside | `Yau Tsim Mong` |

---

## 四、建议接口约定（任务 B / C / D 对接）

* **任务 B（`saved_queries` 建议 `query_code`）**：
  - `Q01_daily_briefing`、`Q02_category_breakdown`、`Q03_station_comparison`、`Q04_weather_pollution`、`Q05_district_map`、`Q06_monthly_summary`、`Q07_high_risk_bulletin`、`Q08_news_flash`、`Q09_report_history`
  - **重要**：`hourly_pollutants` 与 `daily_weather` 已完整入库，但部分小时污染物存在 `NULL`（来自源数据 `N.A.`），因此 `Q01` / `Q03` / `Q04` / `Q06` 仍必须使用 `LEFT JOIN`，保证即使某小时污染物为 `NULL` 也不丢掉 AQHI 行；浓度均值须同时返回有效测量小时数 `COUNT(col)`。
* **任务 B（`src/crud.py`）**：
  - 所有表实现参数化 `create_*` / `get_*` / `update_*` / `delete_*`；删除父表（如 `districts`、`stations`、`saved_queries`、`report_templates`）时须显式检查外键依赖或提供明确异常提示。
* **任务 C（`src/templates.py`）**：
  - 核心渲染函数接收 `(template_name, params_dict)`：查询对应 `saved_queries` → 校验 `required_variables` → 若无有效数据返回明确英文说明（不报错、不编造 0）→ 同步生成 `text_output`、`markdown_output`、`html_output` 并插入 `generated_reports`。
* **任务 D（`src/viz.py`、`src/site_export.py`）**：
  - `viz.py` 函数直接读 `air_quality.db`（或接收查询结果）输出 PNG 到指定路径及生成 Folium HTML 地图；18 区边界可直接用 `data/raw/geo_population/cydalytics_hkg_adm1.geojson`（其中 `properties.name_1` 与 `districts.english_name` 100% 完全一致）或官方 `had_district_boundary.geojson`，站址经纬度直接读 `stations.latitude / longitude`；`site_export.py` 读取 `generated_reports` + PNG + 地图输出到 `docs/` 并生成移动端友好的 `docs/index.html`。
