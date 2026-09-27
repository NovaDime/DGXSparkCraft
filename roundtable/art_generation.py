"""Approved visual requirements; image generation awaits a multimodal adapter."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ArtAsset(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,47}$')
    kind: Literal['item', 'nine_slice', 'sequence']
    description: str = Field(min_length=4, max_length=800)
    trigger: str = Field(min_length=1, max_length=400)
    frames: int = Field(default=1, ge=1, le=16, strict=True)
    fps: int = Field(default=12, ge=1, le=30, strict=True)
    loop: bool = False
    borders: list[int] = Field(default_factory=lambda:[4,4,4,4], min_length=4, max_length=4)

    @model_validator(mode='after')
    def valid(self):
        if self.kind != 'sequence' and self.frames != 1:
            raise ValueError('静态图标和九宫格仅一张图')
        if any(type(x) is not int or not 0 <= x <= 15 for x in self.borders):
            raise ValueError('九宫格边距必须为 0–15 的整数')
        if self.borders[0]+self.borders[2] >= 16 or self.borders[1]+self.borders[3] >= 16:
            raise ValueError('九宫格必须保留中心区域')
        return self

