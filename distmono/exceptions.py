class DistmonoError(Exception):
    pass


class ConfigError(DistmonoError):
    pass


class CircularDependencyError(Exception):
    pass
