class DistmonoError(Exception):
    pass


class ConfigError(DistmonoError):
    pass


class CircularDependencyError(DistmonoError):
    pass


class BuildNotFoundError(DistmonoError):
    pass


class StackDoesNotExistError(DistmonoError):
    pass
