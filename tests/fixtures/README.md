# Protobuf compatibility fixtures

`protobuf-v1.pb` and `protobuf-v2.pb` are `FileDescriptorSet` snapshots of the
SDK's deployed generated modules at `fddffd2a558dbdd79fffb2db934bf3770b8f5bbd`,
before regeneration. They were captured using protobuf 3.20.3. The descriptor
test compares field numbers/types, oneofs, enums, defaults, options and service
definitions, normalizing only compiler metadata that has no wire effect.

`protobuf-wire.json` contains messages serialized by protobuf 3.20.3 on Python
3.9 using those descriptors. They cover every top-level message, the top-level
oneof alternatives, repeated values, non-ASCII strings, binary bytes, negative
integers and unsigned values above 32 bits. The test checks byte-for-byte
round trips and retention of an appended unknown field. Existing historical
claim and wallet signing fixtures provide application-level coverage.

These fixtures represent the old implementation. Do not regenerate them with
the new runtime when updating generated modules.
