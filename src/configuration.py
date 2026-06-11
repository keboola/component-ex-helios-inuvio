from enum import StrEnum

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class LoadType(StrEnum):
    full_load = "full_load"
    incremental_load = "incremental_load"


class Configuration(BaseModel):
    base_url: str
    username: str
    password: str = Field(alias="#password")
    database: str
    browse: str = ""
    output_table_name: str = ""
    columns: list[str] = Field(default_factory=list)
    load_type: LoadType = LoadType.full_load
    primary_key: list[str] = Field(default_factory=list)
    filter: str = ""
    system_parameters: dict[str, str] = Field(default_factory=dict)
    debug: bool = False

    model_config = {"populate_by_name": True}

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            messages = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration validation error: {', '.join(messages)}")
