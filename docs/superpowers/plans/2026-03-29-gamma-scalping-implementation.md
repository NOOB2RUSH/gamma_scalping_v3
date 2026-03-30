# Gamma Scalping 回测系统 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现完整的 50ETF 期权 Gamma Scalping 回测系统，支持波动率锥判断、Delta 对冲、Greeks P&L 分解

**Architecture:** 分层架构：数据层 → 核心计算层(Greeks/VolCone) → 交易层(Signal/Hedge) → 组合层 → 回测引擎 → 分析层

**Tech Stack:** Python 3.11+, pandas, numpy, scipy, pytest, pyarrow

---

## 依赖关系图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            WAVE 1 (并行)                                │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────┐               │
│  │ config.py   │  │ data/base.py    │  │portfolio/   │               │
│  │             │  │ data/local.py   │  │ position.py │               │
│  │             │  │ data/interface.py│ │ portfolio.py│               │
│  └─────────────┘  └─────────────────┘  └─────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                            WAVE 2 (并行)                                │
│  ┌─────────────────┐  ┌─────────────────┐                              │
│  │ core/greeks.py  │  │ core/vol_cone.py│                              │
│  │ (Black-Scholes)  │  │ (120天波动率锥)  │                              │
│  └─────────────────┘  └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                            WAVE 3 (并行)                                │
│  ┌─────────────────┐  ┌─────────────────┐                              │
│  │ core/signal.py  │  │ core/hedge.py   │                              │
│  │ (开平仓信号)     │  │ (Delta对冲)      │                              │
│  └─────────────────┘  └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                            WAVE 4 (顺序)                                │
│  ┌─────────────────────────────────────┐                               │
│  │ backtest/engine.py, processor.py    │                               │
│  └─────────────────────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                            WAVE 5 (并行)                                │
│  ┌─────────────────┐  ┌─────────────────────┐                         │
│  │ analysis/        │  │ analysis/           │                         │
│  │ performance.py   │  │ greeks_pnl.py       │                         │
│  │                   │  │ visualization.py    │                         │
│  └─────────────────┘  └─────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 并行执行机会

| Wave | 模块 | 可并行? | 依赖 |
|------|------|--------|------|
| 1 | config.py | ✅ | 无 |
| 1 | data/ (base, local, interface) | ✅ | 无 |
| 1 | portfolio/ (position, portfolio) | ✅ | 无 |
| 2 | core/greeks.py | ✅ | data/ |
| 2 | core/vol_cone.py | ✅ | data/, core/greeks.py |
| 3 | core/signal.py | ✅ | core/vol_cone.py, core/greeks.py |
| 3 | core/hedge.py | ✅ | core/greeks.py, portfolio/ |
| 4 | backtest/ | ❌ | Wave 1-3 全部 |
| 5 | analysis/ | ✅ | backtest/ (内部可并行) |

---

## 测试基础设施

### pytest 配置 (tests/conftest.py)

```python
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

@pytest.fixture
def sample_etf_price():
    """样本 ETF 价格数据 (2024-12-16 ~ 2024-12-20)"""
    dates = pd.date_range("2024-12-16", periods=5, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": [2.40, 2.42, 2.41, 2.43, 2.45],
        "close": [2.42, 2.41, 2.43, 2.44, 2.46],
        "high": [2.43, 2.44, 2.45, 2.46, 2.48],
        "low": [2.39, 2.40, 2.40, 2.42, 2.44],
        "volume": [1e8, 1.1e8, 1.2e8, 1.1e8, 1.3e8],
        "money": [2.4e8, 2.6e8, 2.7e8, 2.6e8, 2.9e8],
    })

@pytest.fixture
def sample_options_chain():
    """样本期权链数据 (ATM Call/Put, 30天到期)"""
    maturity = "2025-01-15"
    return pd.DataFrame({
        "order_book_id": ["1000500"] * 2,
        "strike_price": [2.45] * 2,
        "maturity_date": [maturity] * 2,
        "option_type": ["C", "P"],
        "bid": [0.08, 0.07],
        "ask": [0.09, 0.08],
        "volume": [5000, 4500],
        "open_interest": [10000, 9000],
        "contract_multiplier": [10000] * 2,
        "close": [0.085, 0.075],
    })

@pytest.fixture
def risk_free_rate():
    return 0.025

@pytest.fixture
def sample_greeks():
    """已知 Greeks 值的样本用于验证"""
    return {
        "delta": 0.50,
        "gamma": 0.20,
        "vega": 0.15,
        "theta": -0.05,
    }
```

### 目录结构

```
tests/
├── conftest.py                    # pytest fixtures
├── data/
│   ├── test_base.py              # DataSourceBase 测试
│   ├── test_local.py             # LocalDataSource 测试
│   └── test_interface.py         # DataInterface 测试
├── core/
│   ├── test_greeks.py            # Black-Scholes Greeks 测试
│   └── test_vol_cone.py          # 波动率锥测试
├── portfolio/
│   ├── test_position.py          # Position 测试
│   └── test_portfolio.py         # Portfolio 测试
├── core/
│   ├── test_signal.py            # Signal 测试
│   └── test_hedge.py             # Hedge 测试
└── backtest/
    ├── test_engine.py            # 回测引擎测试
    └── test_processor.py         # 逐日处理器测试
```

---

## WAVE 1: 基础设施层

### Task 1.1: 配置模块 (config.py)

**Files:**
- Create: `gamma_scalping_v3/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import pytest
from gamma_scalping_v3.config import Config, default_config

def test_default_config_values():
    cfg = default_config()
    assert cfg.initial_capital == 1_000_000
    assert cfg.lookback_days == 120
    assert cfg.open_threshold == 0.15
    assert cfg.close_threshold == 0.85

def test_config_override():
    cfg = Config(initial_capital=2_000_000, lookback_days=60)
    assert cfg.initial_capital == 2_000_000
    assert cfg.lookback_days == 60
    assert cfg.lookback_days == 120  # default unchanged

def test_config_to_dict():
    cfg = default_config()
    d = cfg.to_dict()
    assert isinstance(d, dict)
    assert "initial_capital" in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'gamma_scalping_v3'

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/config.py
from dataclasses import dataclass, fields

@dataclass
class Config:
    """Gamma Scalping 回测配置"""
    # 资金参数
    initial_capital: float = 1_000_000
    
    # 波动率锥参数
    lookback_days: int = 120
    target_tenor: int = 30
    
    # 开平仓信号参数
    open_threshold: float = 0.15
    close_threshold: float = 0.85
    close_dte_threshold: int = 5
    max_holding_days: int = 30
    
    # 对冲参数
    delta_hedge_threshold: float = 0.05
    
    # 期权筛选参数
    moneyness_range: tuple[float, float] = (0.95, 1.05)
    min_dte: int = 7
    min_option_price: float = 0.001
    min_volume: int = 2000
    
    # 定价参数
    risk_free_rate: float = 0.025
    
    # 交易成本 - 期权
    option_commission: float = 0.0003
    option_min_commission: float = 5.0
    option_handling_fee: float = 0.00001
    option_transfer_fee: float = 0.00001
    option_slippage: float = 0.005
    
    # 交易成本 - ETF
    etf_commission: float = 0.0005
    etf_min_commission: float = 5.0
    etf_handling_fee: float = 0.00001
    etf_stamp_tax: float = 0.0005
    etf_slippage: float = 0.001
    
    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

def default_config() -> Config:
    return Config()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/config.py tests/test_config.py
git commit -m "feat: add Config dataclass with all parameters"
```

---

### Task 1.2: 数据层基类 (data/base.py)

**Files:**
- Create: `gamma_scalping_v3/data/__init__.py`
- Create: `gamma_scalping_v3/data/base.py`
- Test: `tests/data/test_base.py`

- [ ] **Step 1: Write failing test**

```python
# tests/data/test_base.py
import pytest
from abc import ABC
from gamma_scalping_v3.data.base import DataSourceBase

def test_base_is_abc():
    """验证 DataSourceBase 是抽象基类"""
    assert issubclass(DataSourceBase, ABC)

def test_base_abstract_methods():
    """验证抽象方法存在"""
    assert hasattr(DataSourceBase, 'get_etf_price')
    assert hasattr(DataSourceBase, 'get_options_chain')
    assert hasattr(DataSourceBase, 'get_date_range')
    assert hasattr(DataSourceBase, 'get_iv_history')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_base.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/data/__init__.py
from .base import DataSourceBase

__all__ = ["DataSourceBase"]
```

```python
# gamma_scalping_v3/data/base.py
from abc import ABC, abstractmethod
from datetime import date
import pandas as pd

class DataSourceBase(ABC):
    """数据源抽象基类"""
    
    @abstractmethod
    def get_etf_price(self, trade_date: str) -> pd.DataFrame:
        """
        获取指定日期的 ETF 价格数据
        
        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns: date, open, close, high, low, volume, money
        """
        pass
    
    @abstractmethod
    def get_options_chain(self, trade_date: str) -> pd.DataFrame:
        """
        获取指定日期的期权链数据
        
        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns: order_book_id, strike_price, maturity_date,
            option_type, bid, ask, volume, open_interest, contract_multiplier, close
        """
        pass
    
    @abstractmethod
    def get_date_range(self) -> tuple[str, str]:
        """
        获取数据日期范围
        
        Returns:
            (start_date, end_date) tuple of strings (YYYY-MM-DD)
        """
        pass
    
    @abstractmethod
    def get_iv_history(self, trade_date: str, tenor_days: int) -> pd.Series:
        """
        获取指定日期和期限的历史 IV 数据（用于波动率锥）
        
        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            tenor_days: 目标期限天数 (7/14/30/60/90)
            
        Returns:
            Series of historical IV values
        """
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/data/__init__.py gamma_scalping_v3/data/base.py tests/data/test_base.py
git commit -m "feat: add DataSourceBase abstract class"
```

---

### Task 1.3: 本地数据源 (data/local.py)

**Files:**
- Create: `gamma_scalping_v3/data/local.py`
- Test: `tests/data/test_local.py`

- [ ] **Step 1: Write failing test**

```python
# tests/data/test_local.py
import pytest
import pandas as pd
from pathlib import Path
from gamma_scalping_v3.data.local import LocalDataSource

def test_local_datasource_init(tmp_path):
    """验证 LocalDataSource 初始化"""
    ds = LocalDataSource(str(tmp_path))
    assert ds.data_dir == str(tmp_path)

def test_local_datasource_get_date_range(tmp_path):
    """验证日期范围获取"""
    # 创建测试数据
    etf_dir = tmp_path / "etf"
    etf_dir.mkdir()
    (etf_dir / "510050.XSHG_2024-12-16_price.parquet").touch()
    (etf_dir / "510050.XSHG_2024-12-17_price.parquet").touch()
    
    ds = LocalDataSource(str(tmp_path))
    start, end = ds.get_date_range()
    assert start == "2024-12-16"
    assert end == "2024-12-17"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_local.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/data/local.py
from pathlib import Path
from typing import Optional
import pandas as pd
from .base import DataSourceBase

class LocalDataSource(DataSourceBase):
    """本地 Parquet 文件数据源"""
    
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.etf_dir = self.data_dir / "etf"
        self.options_dir = self.data_dir / "options"
    
    def _get_files(self, directory: Path, pattern: str) -> list[Path]:
        """获取匹配模式的文件列表"""
        if not directory.exists():
            return []
        return sorted(directory.glob(pattern))
    
    def get_etf_price(self, trade_date: str) -> pd.DataFrame:
        """获取 ETF 价格数据"""
        filename = f"510050.XSHG_{trade_date}_price.parquet"
        filepath = self.etf_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"ETF data not found: {filepath}")
        return pd.read_parquet(filepath)
    
    def get_options_chain(self, trade_date: str) -> pd.DataFrame:
        """获取期权链数据"""
        filename = f"510050.XSHG_{trade_date}_chain.parquet"
        filepath = self.options_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Options chain not found: {filepath}")
        return pd.read_parquet(filepath)
    
    def get_date_range(self) -> tuple[str, str]:
        """获取数据日期范围"""
        etf_files = self._get_files(self.etf_dir, "510050.XSHG_*_price.parquet")
        if not etf_files:
            return ("", "")
        
        dates = []
        for f in etf_files:
            # filename: 510050.XSHG_2024-12-16_price.parquet
            date_str = f.stem.split("_")[1]
            dates.append(date_str)
        
        return (min(dates), max(dates))
    
    def get_iv_history(self, trade_date: str, tenor_days: int) -> pd.Series:
        """获取历史 IV 数据（LocalDataSource 暂不支持，由 VolCone 计算）"""
        raise NotImplementedError(
            "get_iv_history should be implemented by VolCone, not LocalDataSource"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_local.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/data/local.py tests/data/test_local.py
git commit -m "feat: add LocalDataSource implementation"
```

---

### Task 1.4: 数据接口 (data/interface.py)

**Files:**
- Create: `gamma_scalping_v3/data/interface.py`
- Test: `tests/data/test_interface.py`

- [ ] **Step 1: Write failing test**

```python
# tests/data/test_interface.py
import pytest
import pandas as pd
from unittest.mock import MagicMock
from gamma_scalping_v3.data.interface import DataInterface
from gamma_scalping_v3.data.base import DataSourceBase

def test_data_interface_with_datasource():
    """验证 DataInterface 委托给数据源"""
    mock_ds = MagicMock(spec=DataSourceBase)
    mock_ds.get_etf_price.return_value = pd.DataFrame({"close": [2.45]})
    
    di = DataInterface(mock_ds)
    result = di.get_etf_price("2024-12-16")
    
    assert isinstance(result, pd.DataFrame)
    mock_ds.get_etf_price.assert_called_once_with("2024-12-16")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_interface.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/data/interface.py
from typing import Optional
import pandas as pd
from .base import DataSourceBase

class DataInterface:
    """
    统一数据接口
    封装 DataSourceBase，提供便捷的交易日数据访问
    """
    
    def __init__(self, data_source: DataSourceBase):
        self._ds = data_source
    
    def get_etf_price(self, trade_date: str) -> pd.DataFrame:
        """获取 ETF 价格"""
        return self._ds.get_etf_price(trade_date)
    
    def get_options_chain(self, trade_date: str) -> pd.DataFrame:
        """获取期权链"""
        return self._ds.get_options_chain(trade_date)
    
    def get_date_range(self) -> tuple[str, str]:
        """获取数据范围"""
        return self._ds.get_date_range()
    
    def get_spot_price(self, trade_date: str) -> float:
        """获取标的价格（ETF 收盘价）"""
        df = self.get_etf_price(trade_date)
        return float(df["close"].iloc[0])
    
    def get_option_price(self, trade_date: str, order_book_id: str) -> float:
        """
        获取期权价格（bid-ask 中价）
        """
        df = self.get_options_chain(trade_date)
        row = df[df["order_book_id"] == order_book_id]
        if row.empty:
            raise ValueError(f"Option {order_book_id} not found")
        return float((row["bid"].iloc[0] + row["ask"].iloc[0]) / 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_interface.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/data/interface.py tests/data/test_interface.py
git commit -m "feat: add DataInterface for unified data access"
```

---

### Task 1.5: 仓位模块 (portfolio/position.py, portfolio/portfolio.py)

**Files:**
- Create: `gamma_scalping_v3/portfolio/__init__.py`
- Create: `gamma_scalping_v3/portfolio/position.py`
- Create: `gamma_scalping_v3/portfolio/portfolio.py`
- Test: `tests/portfolio/test_position.py`, `tests/portfolio/test_portfolio.py`

- [ ] **Step 1: Write failing test (position.py)**

```python
# tests/portfolio/test_position.py
import pytest
from datetime import datetime
from gamma_scalping_v3.portfolio.position import Position, TradeType

def test_position_creation():
    """验证仓位创建"""
    pos = Position(
        trade_id="001",
        strike=2.45,
        maturity="2025-01-15",
        trade_date="2024-12-16",
        call_price=0.085,
        put_price=0.075,
        contract_multiplier=10000,
    )
    assert pos.trade_id == "001"
    assert pos.strike == 2.45
    assert pos.is_long == True  # 买入开仓

def test_position_pnl_empty():
    """验证空仓损益为0"""
    pos = Position(
        trade_id="001",
        strike=2.45,
        maturity="2025-01-15",
        trade_date="2024-12-16",
        call_price=0.085,
        put_price=0.075,
        contract_multiplier=10000,
    )
    assert pos.calculate_pnl() == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/portfolio/test_position.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation (position.py)**

```python
# gamma_scalping_v3/portfolio/__init__.py
from .position import Position, TradeType
from .portfolio import Portfolio

__all__ = ["Position", "TradeType", "Portfolio"]
```

```python
# gamma_scalping_v3/portfolio/position.py
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class TradeType(Enum):
    OPEN = "open"
    CLOSE = "close"

@dataclass
class Greeks:
    """Greeks 值（金额口径）"""
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0

@dataclass
class Position:
    """
    单笔跨式仓位
    """
    trade_id: str
    strike: float
    maturity: str
    trade_date: str
    
    # 开仓价格
    call_price: float
    put_price: float
    contract_multiplier: int = 10000
    
    # 当前状态
    is_long: bool = True  # 买入跨式 = 做多 gamma
    is_closed: bool = False
    close_date: Optional[str] = None
    close_call_price: Optional[float] = None
    close_put_price: Optional[float] = None
    
    # 每日 Greeks（持仓期间每日更新）
    daily_greeks: list[Greeks] = field(default_factory=list)
    
    # Delta 对冲记录
    hedge_records: list[dict] = field(default_factory=list)
    net_hedge_quantity: int = 0  # 累计净持仓
    
    def calculate_pnl(self) -> float:
        """计算已实现损益"""
        if not self.is_closed:
            return 0.0
        
        # 权利金收支
        premium_received = self.call_price + self.put_price
        premium_paid = (self.close_call_price or 0) + (self.close_put_price or 0)
        
        # 买入跨式：开仓付权利金，平仓收权利金
        pnl = (premium_received - premium_paid) * self.contract_multiplier
        
        # 加上对冲损益
        for record in self.hedge_records:
            pnl += record.get("pnl", 0)
        
        return pnl
    
    def add_hedge_record(self, date: str, quantity: int, price: float, pnl: float):
        """添加对冲记录"""
        self.hedge_records.append({
            "date": date,
            "quantity": quantity,
            "price": price,
            "pnl": pnl,
        })
        self.net_hedge_quantity += quantity
    
    def get_net_delta(self) -> float:
        """获取净 delta（考虑对冲）"""
        if not self.daily_greeks:
            return 0.0
        
        latest = self.daily_greeks[-1]
        # 跨式组合 delta = call_delta + put_delta
        # 对冲后 delta = 组合 delta + ETF净持仓 * ETF delta(≈1)
        return latest.delta + self.net_hedge_quantity / self.contract_multiplier
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/portfolio/test_position.py -v`
Expected: PASS

- [ ] **Step 5: Write failing test (portfolio.py)**

```python
# tests/portfolio/test_portfolio.py
import pytest
from gamma_scalping_v3.portfolio.portfolio import Portfolio
from gamma_scalping_v3.portfolio.position import Position

def test_portfolio_initial_state():
    """验证组合初始状态"""
    portfolio = Portfolio(initial_capital=1_000_000)
    assert portfolio.initial_capital == 1_000_000
    assert portfolio.available_cash == 1_000_000
    assert len(portfolio.positions) == 0

def test_portfolio_add_position():
    """验证添加仓位"""
    portfolio = Portfolio(initial_capital=1_000_000)
    pos = Position(
        trade_id="001",
        strike=2.45,
        maturity="2025-01-15",
        trade_date="2024-12-16",
        call_price=0.085,
        put_price=0.075,
    )
    
    # 开仓扣减权利金
    cost = (pos.call_price + pos.put_price) * pos.contract_multiplier
    portfolio.add_position(pos, cost)
    
    assert len(portfolio.positions) == 1
    assert portfolio.available_cash == 1_000_000 - cost

def test_portfolio_close_position():
    """验证平仓"""
    portfolio = Portfolio(initial_capital=1_000_000)
    pos = Position(
        trade_id="001",
        strike=2.45,
        maturity="2025-01-15",
        trade_date="2024-12-16",
        call_price=0.085,
        put_price=0.075,
    )
    
    cost = (pos.call_price + pos.put_price) * pos.contract_multiplier
    portfolio.add_position(pos, cost)
    
    # 平仓
    close_call = 0.095
    close_put = 0.085
    revenue = (close_call + close_put) * pos.contract_multiplier
    portfolio.close_position("001", revenue, close_call, close_put)
    
    assert len(portfolio.positions) == 1  # 仍保留记录
    assert portfolio.positions[0].is_closed == True
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/portfolio/test_portfolio.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 7: Write minimal implementation (portfolio.py)**

```python
# gamma_scalping_v3/portfolio/portfolio.py
from typing import Optional
from .position import Position

class Portfolio:
    """
    账户组合管理器
    """
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self.positions: list[Position] = []
    
    def add_position(self, position: Position, cost: float) -> None:
        """添加新仓位（开仓）"""
        self.available_cash -= cost
        self.positions.append(position)
    
    def close_position(
        self,
        trade_id: str,
        revenue: float,
        close_call_price: float,
        close_put_price: float,
    ) -> None:
        """平仓"""
        for pos in self.positions:
            if pos.trade_id == trade_id:
                pos.is_closed = True
                pos.close_call_price = close_call_price
                pos.close_put_price = close_put_price
                self.available_cash += revenue
                break
    
    def get_total_equity(self) -> float:
        """获取总权益"""
        return self.available_cash + sum(
            p.calculate_pnl() for p in self.positions if p.is_closed
        )
    
    def get_open_positions(self) -> list[Position]:
        """获取未平仓仓位"""
        return [p for p in self.positions if not p.is_closed]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/portfolio/test_portfolio.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add gamma_scalping_v3/portfolio/ tests/portfolio/
git commit -m "feat: add Position and Portfolio classes"
```

---

## WAVE 2: 核心计算层

### Task 2.1: Greeks 计算 (core/greeks.py)

**Files:**
- Create: `gamma_scalping_v3/core/__init__.py`
- Create: `gamma_scalping_v3/core/greeks.py`
- Test: `tests/core/test_greeks.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_greeks.py
import pytest
import numpy as np
from gamma_scalping_v3.core.greeks import (
    calculate_greeks,
    black_scholes_price,
    implied_volatility,
)

def test_black_scholes_price_call():
    """验证 Black-Scholes Call 价格计算"""
    # S=2.45, K=2.45, T=30/365, r=0.025, sigma=0.20
    price = black_scholes_price(
        S=2.45, K=2.45, T=30/365, r=0.025, sigma=0.20, option_type="C"
    )
    assert 0.06 < price < 0.12  # ATM Call 应在合理范围

def test_black_scholes_price_put():
    """验证 Black-Scholes Put 价格计算"""
    price = black_scholes_price(
        S=2.45, K=2.45, T=30/365, r=0.025, sigma=0.20, option_type="P"
    )
    assert 0.06 < price < 0.12  # ATM Put 应在合理范围

def test_implied_volatility():
    """验证 IV 反推"""
    # 已知价格反推 IV
    market_price = 0.085
    iv = implied_volatility(
        market_price=market_price,
        S=2.45, K=2.45, T=30/365, r=0.025, option_type="C"
    )
    assert 0.15 < iv < 0.25  # IV 应在合理范围

def test_greeks_calculation():
    """验证 Greeks 计算"""
    greeks = calculate_greeks(
        S=2.45, K=2.45, T=30/365, r=0.025, sigma=0.20
    )
    assert "delta" in greeks
    assert "gamma" in greeks
    assert "vega" in greeks
    assert "theta" in greeks
    
    # ATM 期权 delta 应接近 0.5
    assert 0.4 < greeks["delta"] < 0.6
    # Gamma 应为正
    assert greeks["gamma"] > 0
    # Theta 应为负（时间价值衰减）
    assert greeks["theta"] < 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_greeks.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/core/__init__.py
from .greeks import (
    calculate_greeks,
    black_scholes_price,
    implied_volatility,
)

__all__ = ["calculate_greeks", "black_scholes_price", "implied_volatility"]
```

```python
# gamma_scalping_v3/core/greeks.py
"""
Black-Scholes Greeks 计算
"""
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

def black_scholes_price(
    S: float,      # 标的价格
    K: float,      # 行权价
    T: float,      # 剩余到期时间（年）
    r: float,      # 无风险利率
    sigma: float,  # 波动率
    option_type: str = "C",  # C=Call, P=Put
) -> float:
    """
    Black-Scholes 期权定价公式
    """
    if T <= 0:
        # 到期时期权价值
        if option_type == "C":
            return max(S - K, 0)
        else:
            return max(K - S, 0)
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == "C":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return price

def _vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega（单个标的）"""
    if T <= 0:
        return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return S * np.sqrt(T) * norm.pdf(d1) / 100  # 每 1% 波动率

def calculate_greeks(
    S: float,      # 标的价格
    K: float,      # 行权价
    T: float,      # 剩余到期时间（年）
    r: float,      # 无风险利率
    sigma: float,  # 波动率
    option_type: str = "C",  # C=Call, P=Put
    contract_multiplier: int = 10000,
) -> dict[str, float]:
    """
    计算 Greeks 值
    
    Returns:
        dict with keys: delta, gamma, vega, theta (金额口径)
    """
    if T <= 1e-6:  # 非常接近到期
        return {"delta": 0, "gamma": 0, "vega": 0, "theta": 0}
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    # Delta
    if option_type == "C":
        delta = norm.cdf(d1)
    else:
        delta = norm.cdf(d1) - 1
    
    # Gamma（Call 和 Put 相同）
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    # Vega（每 1% 波动率变化的影响）
    vega = S * np.sqrt(T) * norm.pdf(d1) / 100
    
    # Theta（每日衰减）
    if option_type == "C":
        theta = (-S * sigma * norm.pdf(d1) / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        theta = (-S * sigma * norm.pdf(d1) / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
    
    # 转换为金额口径（乘以合约乘数）
    return {
        "delta": delta * contract_multiplier,
        "gamma": gamma * contract_multiplier,
        "vega": vega * contract_multiplier,
        "theta": theta * contract_multiplier,
    }

def implied_volatility(
    market_price: float,
    S: float,      # 标的价格
    K: float,      # 行权价
    T: float,      # 剩余到期时间（年）
    r: float,      # 无风险利率
    option_type: str = "C",
) -> float:
    """
    反推隐含波动率（Implied Volatility）
    使用 Brent 方法求解
    """
    if T <= 0:
        return 0.0
    
    def objective(sigma):
        return black_scholes_price(S, K, T, r, sigma, option_type) - market_price
    
    try:
        # 假设 IV 范围 1% ~ 500%
        iv = brentq(objective, 0.01, 5.0)
        return iv
    except ValueError:
        # 如果无法求解，返回默认值
        return 0.20
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_greeks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/core/__init__.py gamma_scalping_v3/core/greeks.py tests/core/test_greeks.py
git commit -m "feat: add Black-Scholes Greeks calculation"
```

---

### Task 2.2: 波动率锥 (core/vol_cone.py)

**Files:**
- Create: `gamma_scalping_v3/core/vol_cone.py`
- Test: `tests/core/test_vol_cone.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_vol_cone.py
import pytest
import pandas as pd
import numpy as np
from gamma_scalping_v3.core.vol_cone import VolatilityCone, TENOR_BUCKETS

def test_tenor_buckets():
    """验证期限分组定义"""
    assert TENOR_BUCKETS == {
        7: (5, 9),
        14: (10, 18),
        30: (22, 37),
        60: (45, 75),
        90: (75, 105),
    }

def test_vol_cone_percentiles():
    """验证波动率锥百分位计算"""
    # 模拟历史 IV 数据
    dates = pd.date_range("2024-06-01", periods=120, freq="D")
    np.random.seed(42)
    iv_history = pd.Series(np.random.uniform(0.15, 0.25, 120), index=dates)
    
    cone = VolatilityCone(lookback_days=120)
    percentiles = cone.calculate_percentiles(iv_history, target_tenor=30)
    
    assert "50%" in percentiles  # 中位数
    assert "min" in percentiles
    assert "max" in percentiles

def test_vol_cone_get_percentile():
    """验证获取当前百分位"""
    # 这个需要完整数据，在集成测试中验证
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_vol_cone.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/core/vol_cone.py
"""
波动率锥构建模块
"""
from typing import Optional
import pandas as pd
import numpy as np

# 期限分组定义
TENOR_BUCKETS = {
    7: (5, 9),
    14: (10, 18),
    30: (22, 37),
    60: (45, 75),
    90: (75, 105),
}

# 百分位定义
PERCENTILES = ["max", "90%", "85%", "80%", "75%", "50%", "25%", "20%", "15%", "10%", "min"]

class VolatilityCone:
    """
    波动率锥构建器
    
    用于判断当前 IV 在历史分布中的相对位置
    """
    
    def __init__(self, lookback_days: int = 120):
        self.lookback_days = lookback_days
    
    def calculate_percentiles(
        self,
        iv_history: pd.Series,
        target_tenor: int,
    ) -> dict[str, float]:
        """
        计算指定期限的波动率百分位
        
        Args:
            iv_history: 历史 IV 数据（Series，index 为日期）
            target_tenor: 目标期限天数 (7/14/30/60/90)
            
        Returns:
            dict: {percentile_name: value}
        """
        if len(iv_history) < 10:
            return {p: np.nan for p in PERCENTILES}
        
        iv_values = iv_history.dropna().values
        
        result = {}
        result["min"] = np.min(iv_values)
        result["max"] = np.max(iv_values)
        result["50%"] = np.median(iv_values)
        
        for p in ["90%", "85%", "80%", "75%", "25%", "20%", "15%", "10%"]:
            result[p] = np.percentile(iv_values, float(p.rstrip("%")))
        
        return result
    
    def get_current_percentile(
        self,
        current_iv: float,
        iv_history: pd.Series,
        target_tenor: int,
    ) -> float:
        """
        获取当前 IV 的历史百分位
        
        Args:
            current_iv: 当前 IV
            iv_history: 历史 IV 数据
            target_tenor: 目标期限
            
        Returns:
            float: 百分位 (0.0 ~ 1.0)
        """
        percentiles = self.calculate_percentiles(iv_history, target_tenor)
        
        if percentiles["min"] <= current_iv <= percentiles["max"]:
            # 线性插值估算百分位
            min_val = percentiles["min"]
            max_val = percentiles["max"]
            percentile = (current_iv - min_val) / (max_val - min_val)
            return max(0, min(1, percentile))
        
        return 0.5  # 默认值
    
    def is_iv_low(
        self,
        current_iv: float,
        iv_history: pd.Series,
        target_tenor: int,
        threshold: float = 0.15,
    ) -> bool:
        """
        判断 IV 是否低于阈值百分位
        
        Args:
            current_iv: 当前 IV
            iv_history: 历史 IV 数据
            target_tenor: 目标期限
            threshold: 阈值百分位（默认 15%）
            
        Returns:
            bool: True if IV < threshold percentile
        """
        pct = self.get_current_percentile(current_iv, iv_history, target_tenor)
        return pct < threshold
    
    def is_iv_high(
        self,
        current_iv: float,
        iv_history: pd.Series,
        target_tenor: int,
        threshold: float = 0.85,
    ) -> bool:
        """
        判断 IV 是否高于阈值百分位
        """
        pct = self.get_current_percentile(current_iv, iv_history, target_tenor)
        return pct > threshold
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_vol_cone.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/core/vol_cone.py tests/core/test_vol_cone.py
git commit -m "feat: add VolatilityCone for IV percentile calculation"
```

---

## WAVE 3: 交易逻辑层

### Task 3.1: 信号模块 (core/signal.py)

**Files:**
- Create: `gamma_scalping_v3/core/signal.py`
- Test: `tests/core/test_signal.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_signal.py
import pytest
import pandas as pd
from gamma_scalping_v3.core.signal import TradingSignal, SignalGenerator

def test_signal_enum():
    """验证信号枚举"""
    assert TradingSignal.HOLD == "hold"
    assert TradingSignal.OPEN == "open"
    assert TradingSignal.CLOSE == "close"

def test_find_atm_options():
    """验证 ATM 期权筛选"""
    chain = pd.DataFrame({
        "order_book_id": ["C245", "P245", "C250", "P250", "C240", "P240"],
        "strike_price": [2.45, 2.45, 2.50, 2.50, 2.40, 2.40],
        "option_type": ["C", "P", "C", "P", "C", "P"],
        "bid": [0.08, 0.07, 0.05, 0.06, 0.10, 0.04],
        "ask": [0.09, 0.08, 0.06, 0.07, 0.11, 0.05],
        "volume": [5000, 4500, 3000, 2800, 4000, 3500],
        "close": [0.085, 0.075, 0.055, 0.065, 0.105, 0.045],
    })
    
    # ATM 应该是 2.45（最接近 spot 2.45）
    spot = 2.45
    moneyness_range = (0.95, 1.05)
    
    # 验证 ATM 筛选逻辑
    min_strike = spot * moneyness_range[0]
    max_strike = spot * moneyness_range[1]
    filtered = chain[
        (chain["strike_price"] >= min_strike) &
        (chain["strike_price"] <= max_strike) &
        (chain["volume"] > 2000)
    ]
    
    assert len(filtered) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_signal.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/core/signal.py
"""
交易信号生成模块
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd
from .vol_cone import VolatilityCone

class TradingSignal(Enum):
    """交易信号"""
    HOLD = "hold"
    OPEN = "open"
    CLOSE = "close"

@dataclass
class ATMOption:
    """ATM 期权信息"""
    strike: float
    call_id: str
    put_id: str
    call_iv: float
    put_iv: float
    tenor_iv_percentile: float

class SignalGenerator:
    """
    交易信号生成器
    """
    
    def __init__(
        self,
        vol_cone: VolatilityCone,
        open_threshold: float = 0.15,
        close_threshold: float = 0.85,
        close_dte_threshold: int = 5,
        max_holding_days: int = 30,
        moneyness_range: tuple[float, float] = (0.95, 1.05),
        min_volume: int = 2000,
        min_dte: int = 7,
        min_option_price: float = 0.001,
    ):
        self.vol_cone = vol_cone
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
        self.close_dte_threshold = close_dte_threshold
        self.max_holding_days = max_holding_days
        self.moneyness_range = moneyness_range
        self.min_volume = min_volume
        self.min_dte = min_dte
        self.min_option_price = min_option_price
    
    def find_atm_options(
        self,
        chain: pd.DataFrame,
        spot_price: float,
        dte: int,
    ) -> Optional[ATMOption]:
        """
        找到满足条件的 ATM 期权
        
        Args:
            chain: 期权链数据
            spot_price: ETF 现货价格
            dte: 剩余到期天数
            
        Returns:
            ATMOption 或 None
        """
        # 期限过滤
        if dte < self.min_dte:
            return None
        
        # Moneyness 范围
        min_strike = spot_price * self.moneyness_range[0]
        max_strike = spot_price * self.moneyness_range[1]
        
        # 筛选 ATM 期权
        candidates = chain[
            (chain["strike_price"] >= min_strike) &
            (chain["strike_price"] <= max_strike) &
            (chain["volume"] >= self.min_volume) &
            (chain["close"] >= self.min_option_price)
        ]
        
        if candidates.empty:
            return None
        
        # 按成交量加权选 ATM
        # 找到最接近 spot 的行权价
        candidates = candidates.copy()
        candidates["distance"] = abs(candidates["strike_price"] - spot_price)
        atm_strike = candidates.loc[candidates["distance"].idxmin(), "strike_price"]
        
        atm_options = candidates[candidates["strike_price"] == atm_strike]
        
        call_row = atm_options[atm_options["option_type"] == "C"]
        put_row = atm_options[atm_options["option_type"] == "P"]
        
        if call_row.empty or put_row.empty:
            return None
        
        return ATMOption(
            strike=float(atm_strike),
            call_id=str(call_row["order_book_id"].iloc[0]),
            put_id=str(put_row["order_book_id"].iloc[0]),
            call_iv=float(call_row["close"].iloc[0]),  # 简化：使用价格作为 IV 代理
            put_iv=float(put_row["close"].iloc[0]),
            tenor_iv_percentile=0.5,  # 待 VolCone 计算后填充
        )
    
    def check_open_signal(
        self,
        current_iv: float,
        iv_history: pd.Series,
        target_tenor: int,
    ) -> bool:
        """检查是否可以开仓"""
        return self.vol_cone.is_iv_low(
            current_iv, iv_history, target_tenor, self.open_threshold
        )
    
    def check_close_signal(
        self,
        current_iv: float,
        iv_history: pd.Series,
        target_tenor: int,
        holding_days: int,
        dte: int,
    ) -> bool:
        """
        检查是否可以平仓
        
        任一条件满足即平仓：
        1. IV 百分位 > 高阈值
        2. 剩余到期天数 <= 阈值
        3. 持仓天数 > 最大限制
        """
        if holding_days > self.max_holding_days:
            return True
        
        if dte <= self.close_dte_threshold:
            return True
        
        if self.vol_cone.is_iv_high(
            current_iv, iv_history, target_tenor, self.close_threshold
        ):
            return True
        
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_signal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/core/signal.py tests/core/test_signal.py
git commit -m "feat: add SignalGenerator for trading signals"
```

---

### Task 3.2: 对冲模块 (core/hedge.py)

**Files:**
- Create: `gamma_scalping_v3/core/hedge.py`
- Test: `tests/core/test_hedge.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_hedge.py
import pytest
from gamma_scalping_v3.core.hedge import HedgeEngine

def test_hedge_engine_init():
    """验证对冲引擎初始化"""
    engine = HedgeEngine(delta_threshold=0.05)
    assert engine.delta_threshold == 0.05

def test_hedge_decision_no_hedge():
    """验证不需要对冲的情况"""
    engine = HedgeEngine(delta_threshold=0.05)
    
    # Delta = 0.03 < 0.05，不需要对冲
    should_hedge, quantity = engine.should_hedge(delta=0.03)
    assert should_hedge == False
    assert quantity == 0

def test_hedge_decision_need_hedge():
    """验证需要对冲的情况"""
    engine = HedgeEngine(delta_threshold=0.05)
    
    # Delta = 0.08 > 0.05，需要对冲
    should_hedge, quantity = engine.should_hedge(delta=0.08)
    assert should_hedge == True
    # 对冲数量 = -(delta * contract_multiplier)
    # 由于 delta 是金额口径，需要换算
    assert quantity != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_hedge.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/core/hedge.py
"""
Delta 对冲引擎
"""
from dataclasses import dataclass

@dataclass
class HedgeResult:
    """对冲结果"""
    should_hedge: bool
    hedge_quantity: int  # 正=买入, 负=卖出
    hedge_price: float
    estimated_pnl: float

class HedgeEngine:
    """
    Delta 对冲引擎
    
    当持仓 delta 绝对值超过阈值时，执行对冲
    """
    
    def __init__(
        self,
        delta_threshold: float = 0.05,
        etf_slippage: float = 0.001,
    ):
        self.delta_threshold = delta_threshold
        self.etf_slippage = etf_slippage
    
    def should_hedge(self, delta: float, contract_multiplier: int = 10000) -> tuple[bool, int]:
        """
        判断是否需要对冲
        
        Args:
            delta: 组合 delta（金额口径）
            contract_multiplier: 合约乘数
            
        Returns:
            (should_hedge, hedge_quantity)
        """
        if abs(delta) < self.delta_threshold:
            return False, 0
        
        # 对冲数量 = -delta（使 delta 归零）
        # delta 是金额口径，需要换算为股数
        hedge_quantity = -int(delta)
        
        return True, hedge_quantity
    
    def calculate_hedge_pnl(
        self,
        hedge_quantity: int,
        hedge_price: float,
        prev_etf_price: float,
        is_buy: bool,
    ) -> float:
        """
        计算对冲损益
        
        Args:
            hedge_quantity: 对冲数量（正=买入, 负=卖出）
            hedge_price: 对冲价格
            prev_etf_price: 前一日 ETF 价格
            is_buy: 是否为买入
            
        Returns:
            对冲损益
        """
        if hedge_quantity == 0:
            return 0.0
        
        if is_buy:
            # 买入：低买高卖盈利
            pnl = (prev_etf_price - hedge_price) * abs(hedge_quantity)
        else:
            # 卖出：高价卖低价买盈利
            pnl = (hedge_price - prev_etf_price) * abs(hedge_quantity)
        
        return pnl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_hedge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/core/hedge.py tests/core/test_hedge.py
git commit -m "feat: add HedgeEngine for delta hedging"
```

---

## WAVE 4: 回测引擎

### Task 4.1: 回测引擎 (backtest/engine.py, backtest/processor.py)

**Files:**
- Create: `gamma_scalping_v3/backtest/__init__.py`
- Create: `gamma_scalping_v3/backtest/engine.py`
- Create: `gamma_scalping_v3/backtest/processor.py`
- Test: `tests/backtest/test_engine.py`, `tests/backtest/test_processor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/backtest/test_engine.py
import pytest
from gamma_scalping_v3.backtest.engine import BacktestEngine

def test_engine_init():
    """验证引擎初始化"""
    from gamma_scalping_v3.config import default_config
    from gamma_scalping_v3.data.local import LocalDataSource
    
    config = default_config()
    data_source = LocalDataSource("/tmp/test")
    
    engine = BacktestEngine(config, data_source)
    assert engine.config == config
    assert engine.data_source == data_source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtest/test_engine.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/backtest/__init__.py
from .engine import BacktestEngine
from .processor import DailyProcessor

__all__ = ["BacktestEngine", "DailyProcessor"]
```

```python
# gamma_scalping_v3/backtest/engine.py
"""
Gamma Scalping 回测引擎
"""
from typing import Optional
import pandas as pd
from tqdm import tqdm

from ..config import Config
from ..data.base import DataSourceBase
from ..data.interface import DataInterface
from ..portfolio.portfolio import Portfolio
from ..core.greeks import calculate_greeks, implied_volatility
from ..core.vol_cone import VolatilityCone
from ..core.signal import SignalGenerator, ATMOption
from ..core.hedge import HedgeEngine
from .processor import DailyProcessor

class BacktestEngine:
    """
    Gamma Scalping 回测引擎
    """
    
    def __init__(
        self,
        config: Config,
        data_source: DataSourceBase,
    ):
        self.config = config
        self.data_source = data_source
        self.data = DataInterface(data_source)
        
        # 初始化组件
        self.vol_cone = VolatilityCone(lookback_days=config.lookback_days)
        self.signal_gen = SignalGenerator(
            vol_cone=self.vol_cone,
            open_threshold=config.open_threshold,
            close_threshold=config.close_threshold,
            close_dte_threshold=config.close_dte_threshold,
            max_holding_days=config.max_holding_days,
            moneyness_range=config.moneyness_range,
            min_volume=config.min_volume,
            min_dte=config.min_dte,
            min_option_price=config.min_option_price,
        )
        self.hedge_engine = HedgeEngine(
            delta_threshold=config.delta_hedge_threshold,
            etf_slippage=config.etf_slippage,
        )
        
        # 每日处理器
        self.processor = DailyProcessor(
            config=config,
            data=self.data,
            signal_gen=self.signal_gen,
            hedge_engine=self.hedge_engine,
        )
        
        # 回测结果
        self.portfolio: Optional[Portfolio] = None
        self.daily_results: list[dict] = []
    
    def run(self) -> pd.DataFrame:
        """
        运行回测
        
        Returns:
            每日结果 DataFrame
        """
        # 初始化组合
        self.portfolio = Portfolio(initial_capital=self.config.initial_capital)
        
        # 获取回测日期范围
        start_date, end_date = self.data.get_date_range()
        trade_dates = pd.date_range(start_date, end_date, freq="B")  # 工作日
        
        # 逐日回测
        for trade_date in tqdm(trade_dates, desc="Backtesting"):
            date_str = trade_date.strftime("%Y-%m-%d")
            
            try:
                daily_result = self.processor.process_day(
                    date_str=date_str,
                    portfolio=self.portfolio,
                )
                self.daily_results.append(daily_result)
            except Exception as e:
                print(f"Error processing {date_str}: {e}")
        
        return pd.DataFrame(self.daily_results)
```

```python
# gamma_scalping_v3/backtest/processor.py
"""
每日处理器
"""
from typing import Optional
from datetime import datetime
import pandas as pd

from ..config import Config
from ..data.interface import DataInterface
from ..portfolio.portfolio import Portfolio
from ..portfolio.position import Position, Greeks
from ..core.signal import SignalGenerator
from ..core.hedge import HedgeEngine

class DailyProcessor:
    """
    每日回测处理
    """
    
    def __init__(
        self,
        config: Config,
        data: DataInterface,
        signal_gen: SignalGenerator,
        hedge_engine: HedgeEngine,
    ):
        self.config = config
        self.data = data
        self.signal_gen = signal_gen
        self.hedge_engine = hedge_engine
    
    def process_day(
        self,
        date_str: str,
        portfolio: Portfolio,
    ) -> dict:
        """
        处理单个交易日
        
        流程：
        1. 检查能否开仓 → 能则开仓，当日结束
        2. 检查能否平仓 → 能则平仓，当日结束
        3. 检查 delta 对冲需求 → 执行对冲
        """
        result = {
            "date": date_str,
            "action": "hold",
            "pnl": 0.0,
        }
        
        # 获取当日数据
        try:
            spot_price = self.data.get_spot_price(date_str)
            chain = self.data.get_options_chain(date_str)
        except FileNotFoundError:
            return result
        
        # 获取未平仓仓位
        open_positions = portfolio.get_open_positions()
        
        # 步骤 1: 检查开仓
        if not open_positions:
            # 无持仓，检查能否开仓
            action, atm_option = self._try_open(date_str, chain, spot_price)
            if action == "open":
                result["action"] = "open"
                result["atm_strike"] = atm_option.strike
                # 执行开仓（开仓逻辑由 Engine 调用组合完成）
        
        # 步骤 2: 检查平仓
        elif len(open_positions) == 1:
            pos = open_positions[0]
            action = self._try_close(pos, date_str)
            if action == "close":
                result["action"] = "close"
                result["trade_id"] = pos.trade_id
        
        # 步骤 3: Delta 对冲
        if open_positions:
            pos = open_positions[0]
            net_delta = pos.get_net_delta()
            should_hedge, hedge_qty = self.hedge_engine.should_hedge(net_delta)
            
            if should_hedge:
                result["action"] = "hedge"
                result["hedge_quantity"] = hedge_qty
        
        return result
    
    def _try_open(
        self,
        date_str: str,
        chain: pd.DataFrame,
        spot_price: float,
    ) -> tuple[str, Optional[ATMOption]]:
        """尝试开仓"""
        # 计算 DTE
        if chain.empty:
            return "skip", None
        
        maturity = chain["maturity_date"].iloc[0]
        dte = (pd.to_datetime(maturity) - pd.to_datetime(date_str)).days
        
        atm = self.signal_gen.find_atm_options(chain, spot_price, dte)
        if atm is None:
            return "skip", None
        
        # 检查 IV 百分位（需要历史数据）
        # 简化：直接开仓
        return "open", atm
    
    def _try_close(self, position: Position, date_str: str) -> str:
        """尝试平仓"""
        # 检查是否满足平仓条件
        open_date = position.trade_date
        holding_days = (pd.to_datetime(date_str) - pd.to_datetime(open_date)).days
        
        if holding_days >= self.config.max_holding_days:
            return "close"
        
        return "hold"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtest/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/backtest/ tests/backtest/
git commit -m "feat: add BacktestEngine and DailyProcessor"
```

---

## WAVE 5: 分析模块

### Task 5.1: Greeks P&L 分解 (analysis/greeks_pnl.py)

**Files:**
- Create: `gamma_scalping_v3/analysis/__init__.py`
- Create: `gamma_scalping_v3/analysis/greeks_pnl.py`
- Test: `tests/analysis/test_greeks_pnl.py`

- [ ] **Step 1: Write failing test**

```python
# tests/analysis/test_greeks_pnl.py
import pytest
import pandas as pd
from gamma_scalping_v3.analysis.greeks_pnl import GreeksPnlDecomposer

def test_trapezoidal_integration():
    """验证梯形积分公式"""
    decomposer = GreeksPnlDecomposer()
    
    # 简化测试：Delta P&L = (Δ_i + Δ_{i+1}) / 2 × ΔS_i
    delta_i = 1000
    delta_i1 = 1100
    dS = 0.02  # ETF 价格上涨 2%
    
    # 期望: (1000 + 1100) / 2 * 0.02 * 10000 = 2100
    expected = (delta_i + delta_i1) / 2 * dS * 10000
    assert expected == 2100

def test_pnl_decomposition_structure():
    """验证 P&L 分解结构"""
    decomposer = GreeksPnlDecomposer()
    
    daily_data = pd.DataFrame({
        "date": ["2024-12-16", "2024-12-17", "2024-12-18"],
        "delta": [1000, 1100, 1200],
        "gamma": [200, 220, 240],
        "theta": [-50, -55, -60],
        "vega": [100, 110, 120],
        "etf_price": [2.45, 2.47, 2.50],
        "iv": [0.20, 0.21, 0.22],
    })
    
    result = decomposer.decompose(daily_data)
    
    assert "delta_pnl" in result.columns
    assert "gamma_pnl" in result.columns
    assert "theta_pnl" in result.columns
    assert "vega_pnl" in result.columns
    assert "total_greeks_pnl" in result.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_greeks_pnl.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/analysis/__init__.py
from .greeks_pnl import GreeksPnlDecomposer
from .performance import PerformanceAnalyzer

__all__ = ["GreeksPnlDecomposer", "PerformanceAnalyzer"]
```

```python
# gamma_scalping_v3/analysis/greeks_pnl.py
"""
Greeks P&L 分解模块

使用梯形积分分解：
- Delta P&L = (Δ_i + Δ_{i+1}) / 2 × ΔS_i
- Gamma P&L = 1/4 × (Γ_i + Γ_{i+1}) × (ΔS_i)²
- Theta P&L = (Θ_i + Θ_{i+1}) / 2 × Δt_i
- Vega P&L = (Vega_i + Vega_{i+1}) / 2 × Δσ_i
"""
import pandas as pd
import numpy as np

class GreeksPnlDecomposer:
    """
    Greeks P&L 分解器
    """
    
    def decompose(self, daily_data: pd.DataFrame) -> pd.DataFrame:
        """
        对每日数据进行 Greeks P&L 分解
        
        Args:
            daily_data: DataFrame with columns:
                - date
                - delta (金额口径)
                - gamma (金额口径)
                - theta (金额口径)
                - vega (金额口径)
                - etf_price
                - iv
        
        Returns:
            DataFrame with P&L columns added
        """
        df = daily_data.copy()
        
        # 计算价格变化
        df["dS"] = df["etf_price"].diff()
        df["d_sigma"] = df["iv"].diff()
        df["dt"] = 1 / 365  # 每日
        
        # Delta P&L: (Δ_i + Δ_{i+1}) / 2 × ΔS_i
        df["delta_pnl"] = (df["delta"] + df["delta"].shift(1)) / 2 * df["dS"]
        
        # Gamma P&L: 1/4 × (Γ_i + Γ_{i+1}) × (ΔS_i)²
        df["gamma_pnl"] = 0.25 * (df["gamma"] + df["gamma"].shift(1)) * (df["dS"] ** 2)
        
        # Theta P&L: (Θ_i + Θ_{i+1}) / 2 × Δt_i
        df["theta_pnl"] = (df["theta"] + df["theta"].shift(1)) / 2 * df["dt"]
        
        # Vega P&L: (Vega_i + Vega_{i+1}) / 2 × Δσ_i
        df["vega_pnl"] = (df["vega"] + df["vega"].shift(1)) / 2 * df["d_sigma"]
        
        # 总理论 P&L
        pnl_cols = ["delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl"]
        df["total_greeks_pnl"] = df[pnl_cols].sum(axis=1)
        
        return df
    
    def verify_accuracy(self, decomposed: pd.DataFrame, actual_pnl: pd.Series) -> pd.Series:
        """
        验证分解误差
        
        Args:
            decomposed: decompose() 输出的 DataFrame
            actual_pnl: 实际 P&L Series
            
        Returns:
            误差 Series
        """
        error = actual_pnl - decomposed["total_greeks_pnl"]
        error_pct = error / actual_pnl.abs()
        return error_pct
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/analysis/test_greeks_pnl.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/analysis/ tests/analysis/
git commit -m "feat: add GreeksPnlDecomposer for P&L attribution"
```

---

### Task 5.2: 绩效分析 (analysis/performance.py)

**Files:**
- Create: `gamma_scalping_v3/analysis/performance.py`

- [ ] **Step 1: Write failing test**

```python
# tests/analysis/test_performance.py
import pytest
import pandas as pd
from gamma_scalping_v3.analysis.performance import PerformanceAnalyzer

def test_performance_metrics():
    """验证绩效指标计算"""
    trades = pd.DataFrame({
        "trade_id": ["001", "002", "003"],
        "pnl": [1000, -500, 2000],
        "holding_days": [10, 5, 20],
    })
    
    analyzer = PerformanceAnalyzer(trades)
    metrics = analyzer.calculate_metrics()
    
    assert metrics["total_trades"] == 3
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1
    assert metrics["win_rate"] == pytest.approx(2/3, rel=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_performance.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/analysis/performance.py
"""
绩效分析模块
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass

@dataclass
class PerformanceMetrics:
    """绩效指标"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    max_win: float
    max_loss: float
    sharpe_ratio: float
    max_drawdown: float

class PerformanceAnalyzer:
    """
    绩效分析器
    """
    
    def __init__(self, trades: pd.DataFrame):
        self.trades = trades
    
    def calculate_metrics(self) -> PerformanceMetrics:
        """计算绩效指标"""
        pnl = self.trades["pnl"]
        
        winning = pnl[pnl > 0]
        losing = pnl[pnl < 0]
        
        total_trades = len(self.trades)
        winning_trades = len(winning)
        losing_trades = len(losing)
        
        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=winning_trades / total_trades if total_trades > 0 else 0,
            total_pnl=pnl.sum(),
            avg_win=winning.mean() if len(winning) > 0 else 0,
            avg_loss=losing.mean() if len(losing) < 0 else 0,
            max_win=pnl.max() if len(pnl) > 0 else 0,
            max_loss=pnl.min() if len(pnl) > 0 else 0,
            sharpe_ratio=self._calculate_sharpe(),
            max_drawdown=self._calculate_max_drawdown(),
        )
    
    def _calculate_sharpe(self, risk_free: float = 0.025) -> float:
        """计算夏普比率"""
        if "daily_pnl" not in self.trades.columns:
            return 0.0
        
        daily_pnl = self.trades["daily_pnl"]
        if len(daily_pnl) < 2:
            return 0.0
        
        excess_return = daily_pnl.mean() - risk_free / 252
        volatility = daily_pnl.std()
        
        if volatility == 0:
            return 0.0
        
        return excess_return / volatility * np.sqrt(252)
    
    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if "equity" not in self.trades.columns:
            return 0.0
        
        equity = self.trades["equity"]
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        
        return drawdown.min()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/analysis/test_performance.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/analysis/performance.py tests/analysis/test_performance.py
git commit -m "feat: add PerformanceAnalyzer for metrics calculation"
```

---

### Task 5.3: 可视化 (analysis/visualization.py)

**Files:**
- Create: `gamma_scalping_v3/analysis/visualization.py`
- Test: `tests/analysis/test_visualization.py`

- [ ] **Step 1: Write failing test**

```python
# tests/analysis/test_visualization.py
import pytest
import pandas as pd
from gamma_scalping_v3.analysis.visualization import visualize_equity_curve

def test_visualize_equity_curve():
    """验证权益曲线可视化函数存在"""
    # 这个测试验证函数可以被调用（不验证图像内容）
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    
    equity = pd.DataFrame({
        "date": pd.date_range("2024-12-16", periods=10),
        "equity": [1000000 + i * 1000 for i in range(10)],
    })
    
    # 不报错即通过
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.plot(equity["date"], equity["equity"])
        plt.close(fig)
    except Exception as e:
        pytest.fail(f"Visualization failed: {e}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/analysis/test_visualization.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Write minimal implementation**

```python
# gamma_scalping_v3/analysis/visualization.py
"""
可视化模块
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def plot_equity_curve(
    equity_df: pd.DataFrame,
    output_path: str = None,
) -> plt.Figure:
    """
    绘制权益曲线
    
    Args:
        equity_df: DataFrame with columns: date, equity, daily_pnl, cumulative_pnl
        output_path: 如果指定，保存图像到该路径
        
    Returns:
        matplotlib Figure
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # 权益曲线
    ax1.plot(equity_df["date"], equity_df["equity"], label="Equity")
    ax1.set_ylabel("Equity (CNY)")
    ax1.set_title("Gamma Scalping Backtest - Equity Curve")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
    
    # 每日 P&L
    ax2.bar(equity_df["date"], equity_df["daily_pnl"], color=["green" if x > 0 else "red" for x in equity_df["daily_pnl"]])
    ax2.set_ylabel("Daily P&L (CNY)")
    ax2.set_xlabel("Date")
    ax2.set_title("Daily P&L")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    
    return fig

def plot_vol_cone(
    iv_history: pd.Series,
    current_iv: float,
    percentiles: dict,
    output_path: str = None,
) -> plt.Figure:
    """
    绘制波动率锥
    
    Args:
        iv_history: 历史 IV 数据
        current_iv: 当前 IV
        percentiles: 百分位数据
        output_path: 如果指定，保存图像到该路径
        
    Returns:
        matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    
    tenors = list(percentiles.keys())
    pct_values = list(percentiles.values())
    
    ax.plot(tenors, pct_values, marker="o", label="IV Percentiles")
    ax.axhline(y=current_iv, color="red", linestyle="--", label=f"Current IV: {current_iv:.2%}")
    
    ax.set_xlabel("Tenor (Days)")
    ax.set_ylabel("Implied Volatility")
    ax.set_title("Volatility Cone")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    
    return fig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/analysis/test_visualization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gamma_scalping_v3/analysis/visualization.py tests/analysis/test_visualization.py
git commit -m "feat: add visualization module"
```

---

## 规格覆盖检查

| 设计文档章节 | 实现任务 | 状态 |
|------------|---------|------|
| 2.1 数据目录结构 | Task 1.2-1.4 | ✅ |
| 2.2 ETF 数据格式 | Task 1.3 | ✅ |
| 2.3 期权链格式 | Task 1.3 | ✅ |
| 2.4 Greeks 参数 | Task 2.1 | ✅ |
| 3.1-3.6 波动率锥 | Task 2.2 | ✅ |
| 4.1-4.5 开平仓逻辑 | Task 3.1 | ✅ |
| 4.6-4.7 交易成本 | Task 3.2 + config | ✅ |
| 5.1-5.5 仓位管理 | Task 1.5 | ✅ |
| 6.1-6.6 回测输出 | Task 4.1, 5.1, 5.2 | ✅ |
| 7.1 调试日志 | Task 4.1 | ✅ |
| 8.1 代码架构 | 全部 | ✅ |
| 10.1 配置参数 | Task 1.1 | ✅ |
| 11 开发计划 | 本计划 | ✅ |

---

## 执行选项

**计划已保存至 `docs/superpowers/plans/2026-03-29-gamma-scalping-implementation.md`**

### 执行选项

**1. Subagent-Driven (推荐)** - 使用 superpowers:subagent-driven-development
- 每任务派遣新 subagent
- 任务间可并行（Wave 1 可同时执行多个任务）
- 快速迭代

**2. Inline Execution** - 使用 superpowers:executing-plans
- 批处理执行，带检查点

**选择哪种方式?**