from scripts.summarize_kronos_paths import summarize


def test_path_summary_is_probabilistic_not_a_trade_signal():
    result = summarize({
        "current_close": 100,
        "pivot": 103,
        "invalidation": 96,
        "paths": [
            {"close": [101, 104], "low": [99, 100]},
            {"close": [99, 97], "low": [98, 95]},
        ],
    })
    assert result["probability_clears_pivot"] == 0.5
    assert result["probability_touches_invalidation"] == 0.5
    assert "signal" not in result
