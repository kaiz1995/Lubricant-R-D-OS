from .cost import validate_cost
from .doe import validate_doe
from .statistics import validate_statistics
from .optimization import validate_optimization

REGISTRY = {
    "cost": {"validator": validate_cost, "supported_versions": ["0.1.0"], "required_upstream": []},
    "doe": {"validator": validate_doe, "supported_versions": ["0.1.0"], "required_upstream": []},
    "statistics": {"validator": validate_statistics, "supported_versions": ["0.1.0"], "required_upstream": ["doe_result"]},
    "optimization": {"validator": validate_optimization, "supported_versions": ["0.1.0"], "required_upstream": ["statistics_result", "cost_result"]},
}
