# Smart Money Concepts — structural market analysis
"""
Public API for the SMC (Smart Money Concepts) engine.

Import from here to avoid coupling to internal module layout::

    from app.modules.smc import (
        SMCAnalyzer,
        SMCStructure,
        SMCPattern,
        Zone,
        ISMCAnalyzer,
        BaseSMCAnalyzer,
    )
"""

from app.modules.smc.interfaces import (
    ISMCAnalyzer,
    MTFAnalysis,
    SMCPattern,
    SMCStructure,
    TimeframeAnalysis,
    TrendBias,
    Zone,
)
from app.modules.smc.base import BaseSMCAnalyzer
from app.modules.smc.analyzer import SMCAnalyzer

__all__ = [
    "SMCAnalyzer",
    "SMCStructure",
    "SMCPattern",
    "Zone",
    "TrendBias",
    "TimeframeAnalysis",
    "MTFAnalysis",
    "ISMCAnalyzer",
    "BaseSMCAnalyzer",
]
