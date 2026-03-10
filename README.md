# 量化回测框架

基于 Python + backtrader + tushare 的完整回测框架，支持多种策略、风险管理和专业报告生成。

## 项目结构

```
backtest_framework/
├── __init__.py
├── data_loader.py          # 数据加载 (tushare API)
├── position_manager.py     # 仓位管理 & 风险管理
├── performance.py          # 绩效计算和详细指标分析
├── config.py               # 配置管理
├── run_backtest.py         # 主运行脚本包装器
├── run_backtest.sh         # Shell 脚本 (自动运行并输出到 logs)
├── test_reporting.py       # 报告功能测试脚本
├── requirements.txt        # 依赖管理
├── logs                    # 输出日志文件
├── config/                 # 配置文件目录
│   └── default.yaml        # 默认配置
├── backtest/               # 回测引擎核心模块
│   ├── __init__.py
│   ├── strategy.py         # Backtrader 策略类
│   └── run_backtest.py     # 核心回测执行函数
├── reporting/              # 结果报告与可视化
│   ├── __init__.py
│   ├── visualizer.py       # 绘图函数：使用 matplotlib 绘制净值曲线、回撤、成交标记等
│   └── report_generator.py # 整合图表和指标，生成 HTML 报告或保存图片到 results/
├── results/                # 报告输出目录（自动生成）
└── strategies/             # 策略文件夹
    ├── __init__.py
    ├── sma_crossover.py    # 双均线策略
    ├── rsi_strategy.py     # RSI 超买超卖
    ├── macd_strategy.py    # MACD 金叉死叉
    ├── kdj_strategy.py     # KDJ 交叉
    ├── bollinger_strategy.py # 布林带突破
    └── multi_factor_strategy.py # 多因子策略
```

## 核心功能

- ✅ **数据获取**: 支持 tushare API，自动缓存和错误处理
- ✅ **策略系统**: 6种内置策略 (SMA, RSI, MACD, KDJ, Bollinger, 多因子)
- ✅ **仓位管理**: 固定数量和百分比风险两种模式
- ✅ **风险控制**: 止损、止盈、最大回撤限制
- ✅ **绩效分析**: 夏普比率、最大回撤、年化收益等指标
- ✅ **可视化报告**: HTML报告 + 图表 (净值曲线、回撤、收益分布、价格信号)
- ✅ **配置管理**: YAML配置文件，支持参数自定义
- ✅ **命令行接口**: 灵活的参数配置
- ✅ **自动化运行**: Shell脚本一键执行

## 安装依赖

```bash
# 创建 conda 环境
conda create -n quant python=3.9
conda activate quant

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 方法1: 使用 Shell 脚本 (推荐)

直接运行脚本，使用默认参数：

```bash
./run_backtest.sh
```

### 方法2: 命令行运行

```bash
# 基本用法
python run_backtest.py --strategy SMACrossover

# 自定义参数
python run_backtest.py \
  --strategy RSIStrategy \
  --ts_code 000002.SZ \
  --start 20200101 \
  --end 20231231 \
  --cash 200000 \
  --position_type percent \
  --position_value 0.2 \
  --enable_charts

# 查看帮助
python run_backtest.py --help
```

### 方法3: 测试报告功能

```bash
python test_reporting.py
```

## 配置说明

### 策略参数 (config/default.yaml)

```yaml
strategies:
  sma:
    short_window: 10
    long_window: 30
  rsi:
    period: 14
    overbought: 70
    oversold: 30
  # ... 其他策略参数
```

### 风险管理参数

```yaml
risk:
  stop_loss_percent: 0.05      # 5% 止损
  take_profit_percent: 0.10    # 10% 止盈
  max_drawdown_percent: 0.20   # 20% 最大回撤
```

### 仓位管理

```yaml
position:
  default_type: "percent"      # "fixed" 或 "percent"
  default_value: 0.1           # 固定数量或百分比
```

## 输出结果

运行后会在以下位置生成结果：

- `logs`: 回测执行日志
- `results/backtest_report.html`: 完整的HTML报告
- `results/portfolio_value.png`: 净值曲线图
- `results/drawdown.png`: 回撤图
- `results/returns_distribution.png`: 收益分布图
- `results/signals_price.png`: 价格和信号图

## 支持的策略

1. **SMACrossover**: 双均线交叉策略
2. **RSIStrategy**: RSI超买超卖策略
3. **MACDStrategy**: MACD金叉死叉策略
4. **KDJStrategy**: KDJ交叉策略
5. **BollingerStrategy**: 布林带突破策略
6. **MultiFactorStrategy**: 多因子综合策略

## 扩展开发

### 添加新策略

1. 在 `strategies/` 目录创建新策略文件
2. 继承 `SignalGenerator` 类
3. 实现 `generate()` 方法
4. 在 `run_backtest.py` 中添加策略映射

### 自定义报告

修改 `reporting/report_generator.py` 中的HTML模板来自定义报告格式。

## 注意事项

- 需要有效的 tushare token (在环境变量或配置文件中设置)
- 首次运行会下载数据，后续使用缓存
- 图表生成需要 matplotlib 支持
- HTML报告包含所有图表和详细指标

## 许可证

MIT License
cd backtest_framework
./run_backtest.sh
```

查看结果：
```bash
cat logs
```

### 方法2: 命令行参数运行

自定义参数运行：

```bash
python run_backtest.py --strategy RSIStrategy --ts_code 000001.SZ --start 20220101 --end 20221231 --cash 100000 --token your_tushare_token --position_type percent --position_value 0.1
```

#### 命令行参数说明

- `--strategy`: 策略名称 (必需)
  - 选项: SMACrossover, RSIStrategy, MACDStrategy, KDJStrategy, BollingerStrategy, MultiFactorStrategy
- `--ts_code`: 股票代码 (默认: 000001.SZ)
- `--start`: 开始日期 YYYYMMDD (默认: 20210101)
- `--end`: 结束日期 YYYYMMDD (默认: 20231231)
- `--cash`: 初始资金 (默认: 100000)
- `--token`: tushare token (必需，或设置环境变量 TUSHARE_TOKEN)
- `--position_type`: 仓位类型 (fixed 或 percent，默认: percent)
- `--position_value`: 仓位值 (固定数量或百分比，默认: 0.1)

### 方法3: Python 代码调用

```python
from backtest import run
from strategies import RSIStrategy
from position_manager import PercentRisk

# 运行 RSI 策略
records = run(
    ts_code='000001.SZ',
    start='20220101',
    end='20221231',
    cash=100000,
    token='your_tushare_token',
    strategy_class=RSIStrategy,
    signal_kwargs={'period': 14, 'overbought': 70, 'oversold': 30},
    position_mgr=PercentRisk(percent=0.1)
)

# 查看结果
print(records.tail())
from performance import compute_performance
perf = compute_performance(records['value'])
print(perf)
```

### 可用策略

- **SMACrossover**: 双均线交叉策略
- **RSIStrategy**: RSI 超买超卖策略
- **MACDStrategy**: MACD 金叉死叉策略
- **KDJStrategy**: KDJ 交叉策略
- **BollingerStrategy**: 布林带突破策略
- **MultiFactorStrategy**: 多因子策略 (RSI + MACD)

### 仓位管理

- **FixedSize(size)**: 每次交易固定数量
- **PercentRisk(percent)**: 按账户百分比下单

## 示例输出

运行后输出保存在 `logs` 文件中：

```
Starting Portfolio Value: 100000.00
2022-01-21, BUY EXECUTED, Price: 17.45, Size: 1154
2022-01-27, SELL EXECUTED, Price: 16.50, Size: -1154
Final Portfolio Value: 98903.70

Performance metrics:
annual_return: -0.1544
sharpe: -8.4461
max_drawdown: -0.0110
```

## 扩展策略

1. 在 `strategies/` 文件夹中创建新策略文件
2. 实现 `generate(data: pd.DataFrame) -> pd.Series` 方法，返回信号序列 (1=买入, -1=卖出, 0=持有)
3. 在 `strategies/__init__.py` 中添加导入
4. 在 `strategy.py` 中添加导入 (如果需要)

## 注意事项

- Token 设置: 通过 `--token` 参数传入或设置环境变量 `TUSHARE_TOKEN`
- 数据格式: tushare 日线数据，包含 open/high/low/close/volume/amount
- 信号生成: 基于历史数据计算，避免未来数据泄露
- 输出: 所有输出自动重定向到 `logs` 文件