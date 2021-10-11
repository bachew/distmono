from functools import cached_property
from pathlib import Path
import attr


@attr.s(kw_only=True)
class BuildTool:
    base_dir = attr.ib()

    @cached_property
    def temp_dir(self):
        return Path(self.base_dir) / 'tmp'
