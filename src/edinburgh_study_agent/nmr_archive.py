"""Inspect a NOMAD single-experiment ZIP without extracting or changing bytes.

This is transport integrity and Bruker-layout validation, not spectral processing
or scientific validation of the acquisition. Only the standard library is used.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import struct
import unicodedata
import zipfile
import zlib
from pathlib import Path


MAX_MEMBERS = 2000
MAX_PATH_LENGTH = 1024
MAX_COMPRESSION_RATIO = 200
MAX_METADATA_BYTES = 8 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
_RESERVED_NAMES = {"con", "prn", "aux", "nul", "conin$", "conout$"}
_RESERVED_NAMES.update(f"{prefix}{number}" for prefix in ("com", "lpt")
                       for number in (*range(1, 10), "\u00b9", "\u00b2", "\u00b3"))
_ACQUISITION_NAME = re.compile(r"acqu(?:[2-9])?s\Z")


def _safe_component(value: str) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 255
            and value not in (".", "..") and value == value.rstrip(" .")
            and not any(ord(char) < 32 or ord(char) == 127 or char in '\\/:<>"|?*'
                        for char in value)
            and value.split(".", 1)[0].casefold() not in _RESERVED_NAMES)


def _preflight_directory(stream, size: int) -> None:
    """Bound central-directory work before ZipFile constructs member objects."""
    if size < 22:
        raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
    tail_size = min(size, 22 + 65535)
    stream.seek(size - tail_size)
    tail = stream.read(tail_size)
    end = len(tail)
    while True:
        position = tail.rfind(b"PK\x05\x06", 0, end)
        if position < 0:
            raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
        if position + 22 <= len(tail):
            values = struct.unpack_from("<4s4H2IH", tail, position)
            if position + 22 + values[-1] == len(tail):
                break
        end = position
    _, disk, directory_disk, disk_count, count, directory_size, directory_offset, _ = values
    if count > MAX_MEMBERS or disk_count > MAX_MEMBERS:
        raise ValueError("NMR_ARCHIVE_MEMBER_LIMIT")
    if disk or directory_disk or disk_count != count:
        raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
    if directory_size > MAX_METADATA_BYTES:
        raise ValueError("NMR_ARCHIVE_SIZE_LIMIT")
    if directory_offset + directory_size != size - tail_size + position:
        raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
    # The EOCD count is untrusted. Count the actual central records using
    # fixed-size reads before ZipFile allocates its complete member list.
    stream.seek(directory_offset)
    directory_end = directory_offset + directory_size
    observed = 0
    while stream.tell() < directory_end:
        header = stream.read(46)
        if len(header) != 46 or not header.startswith(b"PK\x01\x02"):
            raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
        observed += 1
        if observed > MAX_MEMBERS:
            raise ValueError("NMR_ARCHIVE_MEMBER_LIMIT")
        name_size, extra_size, comment_size, start_disk = struct.unpack_from("<4H", header, 28)
        if start_disk or stream.tell() + name_size + extra_size + comment_size > directory_end:
            raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
        if name_size > MAX_PATH_LENGTH * 4:
            raise ValueError("NMR_ARCHIVE_UNSAFE_PATH")
        stream.seek(name_size + extra_size + comment_size, os.SEEK_CUR)
    if observed != count:
        raise ValueError("NMR_ARCHIVE_INVALID_ZIP")
    stream.seek(0)


def _member_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    name = info.orig_filename
    if name != info.filename or not name or len(name) > MAX_PATH_LENGTH:
        raise ValueError("NMR_ARCHIVE_UNSAFE_PATH")
    parts = tuple((name[:-1] if info.is_dir() else name).split("/"))
    if not all(_safe_component(part) for part in parts):
        raise ValueError("NMR_ARCHIVE_UNSAFE_PATH")
    return parts


def _register_path(parts, is_directory, entries, nodes):
    # Include implicit parent directories so Dir/a and dir/b cannot collide on
    # a case-insensitive host, nor can a regular file double as a parent folder.
    key = "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)
    if key in entries:
        raise ValueError("NMR_ARCHIVE_DUPLICATE_PATH")
    entries.add(key)
    for index in range(1, len(parts) + 1):
        original = "/".join(parts[:index])
        key = unicodedata.normalize("NFC", original).casefold()
        kind = "directory" if index < len(parts) or is_directory else "file"
        existing = nodes.get(key)
        if existing is not None and existing != (original, kind):
            raise ValueError("NMR_ARCHIVE_DUPLICATE_PATH")
        nodes[key] = (original, kind)


def _validate_members(infos, expected, max_bytes):
    if not infos:
        raise ValueError("NMR_ARCHIVE_EMPTY")
    if len(infos) > MAX_MEMBERS:
        raise ValueError("NMR_ARCHIVE_MEMBER_LIMIT")
    entries, nodes, members = set(), {}, []
    total_size = total_compressed = directories = 0
    for info in infos:
        parts = _member_parts(info)
        is_directory = info.is_dir()
        _register_path(parts, is_directory, entries, nodes)
        mode = stat.S_IFMT(info.external_attr >> 16)
        if (mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                or (mode == stat.S_IFDIR and not is_directory)
                or (mode == stat.S_IFREG and is_directory)
                or (info.external_attr & 0x10 and not is_directory)):
            raise ValueError("NMR_ARCHIVE_UNSUPPORTED_ENTRY")
        if info.flag_bits & (0x1 | 0x40 | 0x2000):
            raise ValueError("NMR_ARCHIVE_ENCRYPTED")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError("NMR_ARCHIVE_UNSUPPORTED_COMPRESSION")
        if (info.file_size < 0 or info.compress_size < 0 or info.file_size > max_bytes
                or total_size + info.file_size > max_bytes):
            raise ValueError("NMR_ARCHIVE_SIZE_LIMIT")
        if info.file_size and (not info.compress_size
                               or info.file_size > info.compress_size * MAX_COMPRESSION_RATIO):
            raise ValueError("NMR_ARCHIVE_COMPRESSION_RATIO")
        total_size += info.file_size
        total_compressed += info.compress_size
        if is_directory:
            if info.file_size:
                raise ValueError("NMR_ARCHIVE_UNSUPPORTED_ENTRY")
            if parts != expected[:len(parts)] and parts[:len(expected)] != expected:
                raise ValueError("NMR_ARCHIVE_EXPERIMENT_MISMATCH")
            directories += 1
            members.append((info, None))
        else:
            if len(parts) <= len(expected) or parts[:len(expected)] != expected:
                raise ValueError("NMR_ARCHIVE_EXPERIMENT_MISMATCH")
            members.append((info, "/".join(parts[len(expected):])))
    return members, directories, total_size, total_compressed


def inspect_archive(path: Path, dataset_name: str, experiment_number: str,
                    max_uncompressed_bytes: int = 256 * 1024 * 1024, *, parent_components=()) -> dict:
    """Return a verified manifest, or a stable ``NMR_ARCHIVE_*`` ValueError.

    Member paths in the result are relative to the exact expected experiment
    root. Each member and the complete archive must fit the byte budget. ZIP
    metadata, member count and compression ratio have separate fixed bounds.
    ZIP64 central directories, multipart archives and compression methods other
    than stored/deflate are not accepted by this download validator. The input is opened
    read-only; no extracted files or rewritten container are produced.
    """
    if (not isinstance(parent_components, tuple) or len(parent_components) > 2
            or any(not _safe_component(value) for value in parent_components)
            or not _safe_component(dataset_name) or not _safe_component(experiment_number)
            or isinstance(max_uncompressed_bytes, bool)
            or not isinstance(max_uncompressed_bytes, int) or max_uncompressed_bytes <= 0):
        raise ValueError("NMR_ARCHIVE_ARGUMENT_INVALID")
    try:
        stream = Path(path).open("rb")
    except (OSError, ValueError, TypeError):
        raise ValueError("NMR_ARCHIVE_UNREADABLE") from None
    try:
        with stream:
            archive_size = os.fstat(stream.fileno()).st_size
            if archive_size > max_uncompressed_bytes + MAX_METADATA_BYTES:
                raise ValueError("NMR_ARCHIVE_SIZE_LIMIT")
            _preflight_directory(stream, archive_size)
            with zipfile.ZipFile(stream) as archive:
                infos = archive.infolist()
                members, directories, total_size, total_compressed = _validate_members(
                    infos, (*parent_components, dataset_name, experiment_number), max_uncompressed_bytes)
                manifest = []
                observed_total = 0
                for info, relative in members:
                    digest = hashlib.sha256()
                    observed_size = 0
                    with archive.open(info, "r") as member:
                        while True:
                            chunk = member.read(min(READ_CHUNK_BYTES,
                                                    info.file_size - observed_size + 1))
                            if not chunk:
                                break
                            observed_size += len(chunk)
                            observed_total += len(chunk)
                            if observed_size > info.file_size or observed_total > max_uncompressed_bytes:
                                raise ValueError("NMR_ARCHIVE_SIZE_LIMIT")
                            digest.update(chunk)
                    if observed_size != info.file_size:
                        raise ValueError("NMR_ARCHIVE_INTEGRITY_ERROR")
                    if relative is not None:
                        manifest.append({"path": relative, "size_bytes": observed_size,
                                         "sha256": digest.hexdigest()})
                nonempty = {entry["path"] for entry in manifest if entry["size_bytes"]}
                raw_files = [name for name in ("fid", "ser") if name in nonempty]
                if not raw_files:
                    raise ValueError("NMR_ARCHIVE_MISSING_RAW_DATA")
                if "acqus" not in nonempty:
                    raise ValueError("NMR_ARCHIVE_MISSING_ACQUISITION")
                acquisition_files = ["acqus"] + sorted(
                    name for name in nonempty if name != "acqus" and _ACQUISITION_NAME.fullmatch(name))
                return {"format": "bruker", "member_count": len(infos), "file_count": len(manifest),
                        "directory_count": directories, "archive_size_bytes": archive_size,
                        "total_uncompressed_bytes": total_size,
                        "total_compressed_bytes": total_compressed,
                        "members": sorted(manifest, key=lambda entry: entry["path"]),
                        "raw_files": raw_files, "acquisition_files": acquisition_files}
    except zipfile.BadZipFile:
        raise ValueError("NMR_ARCHIVE_INTEGRITY_ERROR") from None
    except (EOFError, struct.error, zlib.error, RuntimeError, NotImplementedError,
            zipfile.LargeZipFile, UnicodeError):
        raise ValueError("NMR_ARCHIVE_INVALID_ZIP") from None
    except OSError:
        raise ValueError("NMR_ARCHIVE_UNREADABLE") from None
