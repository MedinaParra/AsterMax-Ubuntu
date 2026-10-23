"""Data-only MS-NRBF append writer. It never imports or executes .NET types.

The reader dependency is nrbf==0.1.2. Existing bytes are preserved except for
explicit, verified MemberReference replacements. New metadata uses existing
schemas where available. Value structs with negative IDs are re-emitted inline,
never converted into references to their original enclosing value-type fields.
"""
from dataclasses import dataclass
import math
import struct

import nrbf


def reference(oid):
    return {"__ref__": oid}


def is_reference(value):
    return isinstance(value, dict) and set(value) == {"__ref__"}


class Scanner(nrbf.NRBFParser):
    def __init__(self, data):
        super().__init__(data)
        self.data = data
        self.schemas = {}
        self.instance_schema = {}
        self.member_offsets = {}
        self._resolve = lambda value: value

    def _members(self, oid, names, binary_types, additional):
        values = []
        for name, bt, ai in zip(names, binary_types, additional):
            start = self._f.tell()
            values.append(self._read_value(bt, ai))
            self.member_offsets[(oid, name)] = (start, self._f.tell())
        return values

    def _class(self, system):
        oid, name, names = self._read_class_info()
        binary_types, additional = self._read_member_type_info(len(names))
        library = None if system else self._i32()
        self._class_defs[oid] = (name, names, binary_types, additional)
        self.schemas[oid] = Schema(name, names, binary_types, additional, library)
        self.instance_schema[oid] = oid
        values = self._members(oid, names, binary_types, additional)
        self.objects[oid] = dict(zip(names, values), __class__=name)
        return oid

    def _read_class_with_members_and_types(self):
        return self._class(False)

    def _read_system_class_with_members_and_types(self):
        return self._class(True)

    def _read_class_with_id(self):
        oid, schema_id = self._i32(), self._i32()
        self.instance_schema[oid] = schema_id
        name, names, binary_types, additional = self._class_defs[schema_id]
        values = self._members(oid, names, binary_types, additional)
        self.objects[oid] = dict(zip(names, values), __class__=name)
        return oid

    def raw(self, value):
        visited = set()
        while is_reference(value):
            oid = value["__ref__"]
            if oid in visited:
                raise ValueError("Reference cycle")
            visited.add(oid)
            value = self.objects[oid]
        return value

    def ordered(self, oid):
        value = self.raw(reference(oid))
        keys_list = self.raw(value["_list"])
        keys = self.raw(keys_list["_items"])[:keys_list["_size"]]
        dictionary = self.raw(value["_dictionary"])
        pairs = self.raw(dictionary.get("KeyValuePairs", [])) or []
        mapping = {self.raw(self.raw(p)["key"]): self.raw(p)["value"] for p in pairs}
        return [(self.raw(key), mapping[self.raw(key)]) for key in keys]

    def find(self, class_name):
        return next(oid for oid, value in self.objects.items()
                    if isinstance(value, dict) and value.get("__class__") == class_name)

    def schema_for(self, oid):
        return self.schemas[self.instance_schema[oid]]


@dataclass
class Schema:
    name: str
    names: list
    binary_types: list
    additional: list
    library: object = None

    def replace_type(self, old, new):
        return Schema(self.name.replace(old, new), list(self.names), list(self.binary_types),
                      [a.replace(old, new) if isinstance(a, str) else
                       (a[0].replace(old, new), a[1]) if isinstance(a, tuple) else a
                       for a in self.additional], self.library)


@dataclass
class Inline:
    schema_id: int
    values: dict


class Writer:
    def __init__(self, scanner):
        self.scanner = scanner
        self.next_id = max(abs(i) for i in scanner.objects) + 1
        self.schemas = dict(scanner.schemas)
        self.records = []
        self.created = {}

    def allocate(self, value_type=False):
        oid = self.next_id
        self.next_id += 1
        return -oid if value_type else oid

    @staticmethod
    def integer(value):
        return struct.pack("<i", value)

    @staticmethod
    def string(value):
        raw = value.encode("utf-8")
        n = len(raw)
        prefix = bytearray()
        while n >= 128:
            prefix.append((n & 127) | 128)
            n >>= 7
        prefix.append(n)
        return bytes(prefix) + raw

    def primitive(self, kind, value):
        formats = {1: "?", 2: "B", 6: "d", 7: "h", 8: "i", 9: "q", 10: "b", 11: "f",
                   12: "q", 13: "Q", 14: "H", 15: "I", 16: "Q"}
        if kind == 3:
            return value.encode("utf-8")
        if kind == 5:
            return self.string(str(value))
        if kind not in formats:
            raise ValueError(("Unsupported primitive", kind))
        return struct.pack("<" + formats[kind], value)

    def additional(self, kind, value):
        if kind in [0, 7]:
            return bytes([value])
        if kind == 3:
            return self.string(value)
        if kind == 4:
            return self.string(value[0]) + self.integer(value[1])
        return b""

    def value(self, kind, additional, value):
        if kind == 0:
            return self.primitive(additional, value)
        if value is None:
            return b"\x0a"
        if is_reference(value):
            oid = value["__ref__"]
            if oid < 0:
                # A negative object ID denotes an inline value-type instance.
                return self.class_bytes(self.scanner.instance_schema[oid],
                                        self.scanner.objects[oid], value_type=True)[1]
            return b"\x09" + self.integer(oid)
        if isinstance(value, Inline):
            return self.class_bytes(value.schema_id, value.values, value_type=True)[1]
        if isinstance(value, str):
            oid = self.allocate()
            self.created[oid] = {"kind": "string"}
            return b"\x06" + self.integer(oid) + self.string(value)
        raise TypeError((kind, additional, type(value).__name__))

    def class_bytes(self, schema_id, values, value_type=False, new_schema=None):
        oid = self.allocate(value_type)
        schema = new_schema if new_schema is not None else self.schemas[schema_id]
        if set(values) - {"__class__"} != set(schema.names):
            raise ValueError(("Schema member mismatch", schema.name,
                              sorted(set(values) - {"__class__"}), sorted(schema.names)))
        if new_schema is not None:
            schema_id = oid
            self.schemas[oid] = schema
            data = bytes([4 if schema.library is None else 5]) + self.integer(oid)
            data += self.string(schema.name) + self.integer(len(schema.names))
            data += b"".join(self.string(n) for n in schema.names)
            data += bytes(schema.binary_types)
            data += b"".join(self.additional(k, a) for k, a in zip(schema.binary_types, schema.additional))
            if schema.library is not None:
                data += self.integer(schema.library)
        else:
            data = b"\x01" + self.integer(oid) + self.integer(schema_id)
        data += b"".join(self.value(k, a, values[n]) for n, k, a in
                         zip(schema.names, schema.binary_types, schema.additional))
        self.created[oid] = {"kind": "class", "type": schema.name, "schema_id": schema_id}
        return oid, data

    def new_class(self, schema, values):
        oid, record = self.class_bytes(None, values, new_schema=schema)
        self.records.append(record)
        return reference(oid)

    def clone(self, old_id, overrides=None):
        values = dict(self.scanner.objects[old_id])
        if overrides:
            values.update(overrides)
        oid, record = self.class_bytes(self.scanner.instance_schema[old_id], values)
        self.records.append(record)
        return reference(oid)

    def using_schema(self, schema_id, values):
        oid, record = self.class_bytes(schema_id, values)
        self.records.append(record)
        return reference(oid)

    def primitive_array(self, kind, values):
        oid = self.allocate()
        record = b"\x0f" + self.integer(oid) + self.integer(len(values)) + bytes([kind])
        record += b"".join(self.primitive(kind, value) for value in values)
        self.records.append(record)
        self.created[oid] = {"kind": "primitive_array", "count": len(values), "primitive": kind}
        return reference(oid)

    def string_array(self, values):
        oid = self.allocate()
        record = b"\x11" + self.integer(oid) + self.integer(len(values))
        record += b"".join(self.value(1, None, value) for value in values)
        self.records.append(record)
        self.created[oid] = {"kind": "string_array", "count": len(values)}
        return reference(oid)

    def array(self, kind, additional, values, jagged=False):
        oid = self.allocate()
        record = (b"\x07" + self.integer(oid) + bytes([1 if jagged else 0]) + self.integer(1)
                  + self.integer(len(values)) + bytes([kind]) + self.additional(kind, additional))
        record += b"".join(self.value(kind, additional, value) for value in values)
        self.records.append(record)
        self.created[oid] = {"kind": "typed_array", "count": len(values)}
        return reference(oid)

    def inline(self, old_id, overrides=None):
        values = dict(self.scanner.objects[old_id])
        if overrides:
            values.update(overrides)
        return Inline(self.scanner.instance_schema[old_id], values)

    @staticmethod
    def prime_at_least(n):
        n = max(3, n)
        while any(n % k == 0 for k in range(2, math.isqrt(n) + 1)):
            n += 1
        return n

    def dictionary(self, template_id, pairs, value_type_override=None):
        old = self.scanner.objects[template_id]
        schema = self.scanner.schema_for(template_id)
        if "KeyValuePairs" not in old:
            # Derive the populated Dictionary serialization schema, preserving
            # the exact generic type arguments of the requested dictionary.
            populated = next(i for i, v in self.scanner.objects.items()
                             if isinstance(v, dict) and v.get("__class__", "").startswith(
                                 "System.Collections.Generic.Dictionary`2") and "KeyValuePairs" in v
                             and self.scanner.raw(v.get("KeyValuePairs")))
            source = self.scanner.schema_for(populated)
            generic_arguments = schema.name[len("System.Collections.Generic.Dictionary`2"):]
            pair_type = "System.Collections.Generic.KeyValuePair`2" + generic_arguments
            schema = Schema(schema.name, list(source.names), list(source.binary_types),
                            list(source.additional), source.library)
            schema.additional[schema.names.index("KeyValuePairs")] = pair_type + "[]"
            # Derive key and value types from a populated pair of a compatible
            # dictionary; custom overrides cover absent abstract base types.
            source_pair = self.scanner.raw(self.scanner.raw(self.scanner.objects[populated]["KeyValuePairs"])[0])
            source_pair_id = next(i for i, v in self.scanner.objects.items() if v is source_pair)
            pair_schema = self.scanner.schema_for(source_pair_id)
            pair_schema = Schema(pair_type, list(pair_schema.names), list(pair_schema.binary_types),
                                 list(pair_schema.additional), pair_schema.library)
            if value_type_override is None:
                raise ValueError("A value type override is required for an empty dictionary template")
            pair_schema.binary_types = [1, 4]
            pair_schema.additional = [None, value_type_override]
            # Metadata is defined on the first inline struct of the typed array.
            return self._dictionary_new_schema(old, schema, pair_schema, pairs)
        pair_items = self.scanner.raw(old["KeyValuePairs"])
        pair_id = pair_items[0]["__ref__"]
        pair_schema_id = self.scanner.instance_schema[pair_id]
        pair_schema = self.schemas[pair_schema_id]
        inline_pairs = [Inline(pair_schema_id, dict(key=k, value=v)) for k, v in pairs]
        array = self.array(3, pair_schema.name, inline_pairs)
        return self.clone(template_id, {"Version": len(pairs), "HashSize": self.prime_at_least(len(pairs)),
                                        "KeyValuePairs": array})

    def _dictionary_new_schema(self, template, schema, pair_schema, pairs):
        oid = self.allocate()
        record = (b"\x07" + self.integer(oid) + b"\x00" + self.integer(1) + self.integer(len(pairs))
                  + b"\x03" + self.string(pair_schema.name))
        first_id = None
        for key, value in pairs:
            if first_id is None:
                first_id, b = self.class_bytes(None, dict(key=key, value=value), value_type=True,
                                                new_schema=pair_schema)
            else:
                _, b = self.class_bytes(first_id, dict(key=key, value=value), value_type=True)
            record += b
        self.records.append(record)
        self.created[oid] = {"kind": "typed_array", "count": len(pairs)}
        values = {"Version": len(pairs), "Comparer": template["Comparer"],
                  "HashSize": self.prime_at_least(len(pairs)), "KeyValuePairs": reference(oid)}
        return self.new_class(schema, values)

    def ordered(self, template_id, pairs, value_type_override=None):
        old = self.scanner.objects[template_id]
        list_id = old["_list"]["__ref__"]
        items = self.string_array([key for key, value in pairs])
        ordered_list = self.clone(list_id, {"_items": items, "_size": len(pairs), "_version": len(pairs)})
        dictionary_id = old["_dictionary"]["__ref__"]
        if not pairs:
            original = self.scanner.objects[dictionary_id]
            changes = {"Version": 0, "HashSize": 0}
            if "KeyValuePairs" in original:
                changes["KeyValuePairs"] = None
            dictionary = self.clone(dictionary_id, changes)
        else:
            dictionary = self.dictionary(dictionary_id, pairs, value_type_override)
        return self.clone(template_id, {"_list": ordered_list, "_dictionary": dictionary})

    def finish(self, replacements):
        original = bytearray(self.scanner.data)
        if original[-1] != 11 or self.scanner._f.tell() != len(original):
            raise ValueError("Input was not consumed through its final MessageEnd")
        for (oid, member), target in replacements.items():
            start, end = self.scanner.member_offsets[(oid, member)]
            old = self.scanner.objects[oid][member]
            expected = b"\x09" + self.integer(old["__ref__"])
            if end - start != 5 or bytes(original[start:end]) != expected:
                raise ValueError("Only an existing five-byte MemberReference can be replaced")
            original[start:end] = b"\x09" + self.integer(target["__ref__"])
        return bytes(original[:-1]) + b"".join(self.records) + b"\x0b"


def validate_references(scanner):
    missing = []
    def visit(value):
        if is_reference(value):
            if value["__ref__"] not in scanner.objects:
                missing.append(value["__ref__"])
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
    for value in scanner.objects.values():
        visit(value)
    if missing:
        raise ValueError(("Dangling references", sorted(set(missing))))
    for oid, value in scanner.objects.items():
        if oid in scanner.instance_schema:
            schema = scanner.schema_for(oid)
            if set(value) - {"__class__"} != set(schema.names):
                raise ValueError(("Invalid class members", oid, schema.name))
    return {"objects": len(scanner.objects), "schemas": len(scanner.schemas),
            "dangling_references": 0, "class_member_mismatches": 0}
