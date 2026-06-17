"""Strategy library: pluggable, registered strategies held to the honest bar.

Importing this package registers the built-in strategies (breakout, pullback,
earnings_drift) so the registry is populated and the evaluation harness can score
them automatically.
"""

from strategies import breakout, earnings_drift, pullback  # noqa: F401  (register on import)
