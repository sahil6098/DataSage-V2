from collections import defaultdict

from app.utils.serialization import normalize_value


def flatten_document(document: dict, prefix: str = "", max_depth: int = 2) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for key, value in document.items():
        new_key = f"{prefix}.{key}" if prefix else str(key)
        if max_depth > 0 and isinstance(value, dict):
            flattened.update(flatten_document(value, new_key, max_depth=max_depth - 1))
        else:
            flattened[new_key] = value
    return flattened


def infer_mongo_type(value: object) -> str:
    if value is None:
        return "unknown"
    lowered = type(value).__name__.lower()
    if lowered in {"int", "int64"}:
        return "integer"
    if lowered in {"float", "decimal128"}:
        return "float"
    if lowered in {"bool", "boolean"}:
        return "boolean"
    if lowered in {"datetime", "timestamp"}:
        return "datetime"
    if lowered == "objectid":
        return "objectid"
    if lowered in {"list", "tuple"}:
        return "array"
    if lowered == "dict":
        return "object"
    return "string"


def collection_schema_from_samples(
    sample_documents: list[dict],
    field_descriptions: dict[str, str] | None = None,
) -> list[dict]:
    field_descriptions = field_descriptions or {}
    samples_map: dict[str, list[str]] = defaultdict(list)
    type_map: dict[str, str] = {}
    nullable_map: dict[str, bool] = defaultdict(bool)

    for document in sample_documents:
        flattened = flatten_document(document)
        for field_name, value in flattened.items():
            if value is None:
                nullable_map[field_name] = True
                continue
            type_map.setdefault(field_name, infer_mongo_type(value))
            if len(samples_map[field_name]) < 3:
                samples_map[field_name].append(str(normalize_value(value)))

    fields = []
    for field_name in sorted(set(list(samples_map.keys()) + list(type_map.keys()) + list(field_descriptions.keys()))):
        fields.append(
            {
                "name": field_name,
                "type": type_map.get(field_name, "unknown"),
                "nullable": nullable_map.get(field_name, True),
                "samples": samples_map.get(field_name, []),
                "description": field_descriptions.get(field_name),
            }
        )
    return fields


def normalize_documents(documents: list[dict]) -> list[dict]:
    return [normalize_value(document) for document in documents]
