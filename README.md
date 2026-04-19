# 量化回测框架

基于 Python + backtrader + tushare 的模块化回测框架，支持多策略、仓位管理、风险控制、绩效分析和可视化报告。

## 项目结构

```text
backtest_framework/
├── __init__.py
├── run_backtest.py               # 主运行脚本（根目录入口）
├── run_backtest.sh               # 一键运行脚本（根目录入口）
├── requirements.txt              # 依赖
├── config/                       # 配置模块
│   ├── __init__.py
│   ├── config.py                 # 配置读取
│   └── default.yaml              # 默认配置
├── data_loader/                  # 数据加载模块
│   ├── __init__.py
│   ├── data_loader.py            # tushare 数据加载
│   └── load_csv.py               # 本地 CSV 导入示例
├── backtest/                     # 回测核心模块
│   ├── __init__.py
│   ├── rotation_strategy.py      # Backtrader 多标的轮动执行策略
│   ├── position_manager.py       # 仓位管理 + 风控
│   └── performance.py            # 绩效指标计算
├── reporting/                    # 可视化与报告
│   ├── __init__.py
│   ├── visualizer.py
│   └── report_generator.py
├── strategies/                   # 信号策略
│   ├── __init__.py
│   ├── etf_linear_momentum_rotation.py
│   └── etf_trend_corr_rotation.py
└── results/                      # 结果输出目录
```

## 安装依赖

```bash
conda create -n quant python=3.9 -y
conda activate quant
pip install -r requirements.txt
```

## 运行方式

### 方式1：一键运行（推荐）

```bash
cd backtest_framework
./run_backtest.sh
```

### 方式2：命令行运行

```bash
python run_backtest.py

# 指定配置文件（可选）
python run_backtest.py --config config/default.yaml

python run_backtest.py --help
```

## 命令行参数

- `--config`：配置文件路径（默认 `config/default.yaml`）

## 配置说明

默认配置文件：`config/default.yaml`

- `data.token`：tushare token（统一从配置文件读取）
- `backtest.default_strategy`：默认策略名称
- `backtest.default_start/default_end/default_cash`：回测基础参数
- `strategies`：策略参数
- `visualization`：图表输出路径及开关

## Python 调用示例

```python
from run_backtest import run
from strategies import ETFSafeDogRotation
from backtest.performance import compute_performance

records, trades = run(
    start='20220101',
    end='20221231',
    cash=100000,
    token='your_tushare_token',
    strategy_class=ETFSafeDogRotation,
    signal_kwargs={
        'etf_pool': ['518880.XSHG', '513100.XSHG', '159915.XSHE', '510180.XSHG'],
        'm_days': 25,
        'top_n': 1,
    },
    enable_charts=True,
)

perf = compute_performance(records['value'])
print(perf)
```

## 输出结果

运行后默认输出：

- `results/backtest.log`：执行日志
- `results/backtest_report.html`：HTML 回测报告
- `results/portfolio_value.png`：净值曲线
- `results/drawdown.png`：回撤图
- `results/returns_distribution.png`：收益分布
- `results/signals_price.png`：价格与信号图

## 扩展开发

### 添加新策略

1. 在 `strategies/` 下新增策略文件
2. 实现 `generate_targets(close_panel)` 返回每个交易日目标标的代码
3. 在 `strategies/__init__.py` 导出策略类
4. 在 `run_backtest.py` 的 `strategy_map` 注册策略

### 自定义报告模板

修改 `reporting/report_generator.py` 中模板或上下文字段。

## 注意事项

- 需配置有效 tushare token
- 当前仅保留多标的ETF轮动策略
- 首次运行会下载数据，后续按缓存策略复用
- 图表生成依赖 matplotlib

## 许可证

MIT License
