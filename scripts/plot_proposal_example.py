from pathlib import Path
import csv
import os
import glob
import sys

PROJECT = Path(__file__).resolve().parents[1]
FIGURES = PROJECT / 'proposal' / 'figs'
FIGURES.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(PROJECT / 'scripts' / '.matplotlib'))
sys.path.insert(0, str(PROJECT / '.python_dependencies'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 清理旧字体缓存并重建。
for p in glob.glob(os.path.expanduser('~/.cache/matplotlib/fontlist*.json')):
    os.remove(p)
for p in glob.glob(os.path.expanduser('~/.matplotlib/fontList*.cache')):
    try:
        os.remove(p)
    except FileNotFoundError:
        pass
fm._load_fontmanager(try_read_cache=False)

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams.update({
    'font.size': 10.5,
    'axes.labelsize': 10.5,
    'xtick.labelsize': 9.5,
    'ytick.labelsize': 9.5,
    'axes.edgecolor': '#9BA8B3',
    'axes.labelcolor': '#273746',
    'xtick.color': '#4B5965',
    'ytick.color': '#4B5965',
    'text.color': '#21313E',
    'savefig.facecolor': 'white',
})

SOURCE = PROJECT / 'data' / 'raw' / 'aqhi_2025' / '202504_Eng.csv'
DATE = '2025-04-01'
STATION = 'Central/Western'
rows = list(csv.reader(SOURCE.read_text(encoding='utf-8-sig').splitlines()))
header_i = next(i for i, row in enumerate(rows) if row[:2] == ['Date', 'Hour'])
column = rows[header_i].index(STATION)
date = None
hours, values = [], []
for row in rows[header_i + 1:]:
    if len(row) <= column:
        continue
    if row[0].strip():
        date = row[0].strip()
    if date != DATE or not row[1].strip().isdigit():
        continue
    value = row[column].strip()
    if not value.isdigit():
        raise ValueError(f'The example requires complete, unflagged numeric data: {row}')
    hours.append(int(row[1]))
    values.append(int(value))
assert hours == list(range(1, 25)), hours
assert all(1 <= value <= 10 for value in values)
counts = [sum(1 <= x <= 3 for x in values), sum(4 <= x <= 6 for x in values),
          sum(x == 7 for x in values), sum(8 <= x <= 10 for x in values), 0]
assert sum(counts) == len(values)
assert counts == [19, 5, 0, 0, 0]
peak = max(values)
peak_hours = [hour for hour, value in zip(hours, values) if value == peak]
assert peak == 4 and peak_hours == [17, 18, 19, 20, 21]

def base_axes(title):
    fig, ax = plt.subplots(figsize=(8.2, 2.85))
    fig.subplots_adjust(left=0.085, right=0.97, bottom=0.21, top=0.76)
    fig.text(0.085, 0.96, title, ha='left', va='top', fontsize=13, weight='bold')
    fig.text(0.085, 0.85, 'Central/Western, 1 April 2025 (24 valid hourly records)',
             ha='left', va='top', fontsize=9.2, color='#566775')
    ax.spines[['top', 'right']].set_visible(False)
    return fig, ax

fig, ax = base_axes('Hourly AQHI at Central/Western')
ax.axhspan(0.5, 3.5, color='#EAF4EF', zorder=0)
ax.axhspan(3.5, 6.5, color='#FFF3DD', zorder=0)
ax.axhline(3.5, color='#C6B488', linewidth=0.7, linestyle='--', zorder=1)
ax.plot(hours, values, color='#285F8F', linewidth=2, marker='o', markersize=3.3, zorder=3)
ax.scatter(peak_hours, [peak] * len(peak_hours), color='#C47A16', s=22, zorder=4)
ax.annotate('Daily maximum: 4\n17:00 to 21:00', xy=(19, 4), xytext=(15, 5.8),
            fontsize=9.5, ha='center', va='top',
            arrowprops={'arrowstyle': '-', 'color': '#9D6F24', 'linewidth': 1})
ax.text(23.8, 5.8, 'Moderate (4-6)', fontsize=9, color='#916517', ha='right')
ax.text(23.8, 1.0, 'Low (1-3)', fontsize=9, color='#3C725D', ha='right')
ax.set(xlim=(0.5, 24.5), ylim=(0.5, 6.5), xlabel='Hour', ylabel='AQHI')
ax.set_xticks([1, 3, 6, 9, 12, 15, 18, 21, 24])
ax.set_yticks(range(1, 7))
ax.grid(axis='x', linewidth=0.4, alpha=0.16)
fig.savefig(FIGURES / 'aqhi_hourly_20250401_central_western.png', dpi=300, bbox_inches='tight')
plt.close(fig)

fig, ax = base_axes('Hours in each AQHI health risk category')
fig.subplots_adjust(left=0.23, right=0.97)
labels = ['Low (1-3)', 'Moderate (4-6)', 'High (7)', 'Very high (8-10)', 'Serious (10+)']
colors = ['#4E9B7A', '#DDA13C', '#C6CDD3', '#C6CDD3', '#C6CDD3']
ax.barh(range(5), counts, height=0.59, color=colors, zorder=3)
for i, count in enumerate(counts):
    ax.text(count + 0.35, i, f'{count} h ({count / 24 * 100:.1f}%)', va='center', fontsize=9.8)
ax.set_yticks(range(5), labels)
ax.invert_yaxis()
ax.set(xlim=(0, 25.7), xlabel='Hours out of 24 valid records')
ax.set_xticks([0, 6, 12, 18, 24])
ax.tick_params(axis='y', length=0, pad=9)
ax.spines['left'].set_visible(False)
ax.grid(axis='x', linewidth=0.7, color='#E2E7EB', zorder=0)
fig.savefig(FIGURES / 'aqhi_categories_20250401_central_western.png', dpi=300, bbox_inches='tight')
plt.close(fig)

common = f'''\n\n数据来源：环保署 2025 年 4 月 AQHI 英文 CSV，`{SOURCE.name}`。\n\n官方数据链接：https://www.aqhi.gov.hk/epd/ddata/html/history/2025/202504_Eng.csv\n\n站点：{STATION}。日期：{DATE}。AQHI 为无物理单位的指数等级。图中全部文字为英文。\n\n筛选口径：按源文件日期向下补全日期，只保留小时编号 01 至 24，排除 Daily Max 汇总行。该样本有 24 个有效记录，无缺失和星号标记。小时 24 沿用源文件所属日的编号。\n\n绘图脚本：`../../scripts/plot_proposal_example.py`。\n'''
(FIGURES / 'aqhi_hourly_20250401_central_western.md').write_text(
    '# 中西区站逐小时 AQHI 变化图\n\n横轴为源文件小时编号，纵轴为 AQHI 等级。点为逐小时发布记录，连线仅引导阅读，不代表小时之间的连续观测或插值。浅绿和浅黄背景区分低和中等级。最高 AQHI 为 4，出现在 17、18、19、20、21 时。颜色用于区分类别，不代表额外测量值。' + common,
    encoding='utf-8')
(FIGURES / 'aqhi_categories_20250401_central_western.md').write_text(
    '# 中西区站健康风险等级小时分布图\n\n横轴为小时数，纵轴为五个官方健康风险等级。低等级为 19 小时，占 79.2%；中等级为 5 小时，占 20.8%；高、甚高、严重等级均为 0 小时。百分比分母为当天 24 个有效小时。等级边界为低 1 至 3、中 4 至 6、高 7、甚高 8 至 10、严重 10+。10+ 是单独等级，不按数值 11 处理。\n\n等级来源：https://www.aqhi.gov.hk/en/what-is-aqhi/about-aqhi.html' + common,
    encoding='utf-8')
print({'hours': len(hours), 'category_counts': counts, 'peak': peak, 'peak_hours': peak_hours})
print(FIGURES)
