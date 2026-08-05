import math
import struct
from typing import Any


FORMATS = {
    "int16": "h", "uint16": "H", "int32": "i", "uint32": "I",
    "int64": "q", "uint64": "Q", "float32": "f", "float64": "d",
}


def _register_bytes(registers: list[int], byte_order: str, word_order: str) -> bytes:
    words = list(registers)
    if word_order == "little":
        words.reverse()
    chunks = [int(word).to_bytes(2, "big", signed=False) for word in words]
    if byte_order == "little":
        chunks = [chunk[::-1] for chunk in chunks]
    return b"".join(chunks)


def decode_registers(registers: list[int], definition: dict[str, Any]) -> float | int | bool | str:
    data_type = definition["data_type"]
    if data_type == "boolean":
        raw: Any = bool(registers[0])
    elif data_type == "bit_field":
        bit = int(definition.get("bit", 0))
        raw = bool((registers[0] >> bit) & 1)
    elif data_type == "ascii":
        raw = _register_bytes(registers, definition.get("byte_order", "big"), definition.get("word_order", "big")).decode("ascii", errors="replace").rstrip("\x00 ")
    else:
        payload = _register_bytes(registers, definition.get("byte_order", "big"), definition.get("word_order", "big"))
        raw = struct.unpack(">" + FORMATS[data_type], payload)[0]
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = raw * float(definition.get("scale", 1)) + float(definition.get("offset", 0))
        if isinstance(raw, float) and not math.isfinite(raw):
            raise ValueError("decoded value is not finite")
    enum = definition.get("enum")
    if enum:
        return enum.get(str(int(raw)), str(raw))
    return raw

