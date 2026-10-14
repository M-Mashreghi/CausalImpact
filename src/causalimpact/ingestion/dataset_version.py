"""Content-addressed versions for analysis datasets.

The hash covers column names, dtypes and values. Column order is canonicalised (sorted)
because it carries no meaning; row order is *kept* because seeded procedures such as fold
assignment or bootstrap resampling depend on it. The pandas index is ignored.
"""

from __future__ import annotations

import hashlib

import pandas as pd
from pydantic import BaseModel, ConfigDict


class ColumnSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    dtype: str


class DatasetVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content_hash: str
    n_rows: int
    columns: tuple[ColumnSchema, ...]


def dataset_version(df: pd.DataFrame) -> DatasetVersion:
    if not df.columns.is_unique:
        raise ValueError("dataset columns must be unique to be versioned")
    names = [str(c) for c in df.columns]
    if len(set(names)) != len(names):
        raise ValueError("dataset column names must be unique as strings")
    hasher = hashlib.sha256()
    hasher.update(f"rows={len(df)};".encode())
    columns: list[ColumnSchema] = []
    for name, column in sorted(zip(names, df.columns, strict=True)):
        series = df[column].reset_index(drop=True)
        dtype = str(series.dtype)
        columns.append(ColumnSchema(name=name, dtype=dtype))
        hasher.update(f"col={name!r};dtype={dtype};".encode())
        values = pd.util.hash_pandas_object(series, index=False, categorize=False)
        hasher.update(values.to_numpy(dtype="<u8").tobytes())
    return DatasetVersion(
        content_hash="sha256:" + hasher.hexdigest(),
        n_rows=len(df),
        columns=tuple(columns),
    )
