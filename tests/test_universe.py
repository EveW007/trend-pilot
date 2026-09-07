from trendpilot.config import UniverseConfig
from trendpilot.universe import _parse_nasdaq, _parse_other


def test_parses_and_filters_symbol_directories():
    nasdaq = "Symbol|Security Name|Test Issue|Financial Status|ETF\nAAPL|Apple Inc. - Common Stock|N|N|N\nQQQ|ETF Trust|N|N|Y\nBADW|Bad Co Warrant|N|N|N\nFile Creation Time: 0101202612:00||||\n"
    other = "ACT Symbol|Security Name|Exchange|ETF|Test Issue\nBRK.B|Berkshire Hathaway Class B|N|N|N\nSPY|SPDR ETF|P|Y|N\nFile Creation Time: 0101202612:00||||\n"
    cfg = UniverseConfig(include_etfs=False)
    symbols = [entry.symbol for entry in _parse_nasdaq(nasdaq, cfg) + _parse_other(other, cfg)]
    assert symbols == ["AAPL", "BRK-B"]
