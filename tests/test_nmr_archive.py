"""Synthetic checks for intact, bounded Bruker experiment ZIP validation."""
import hashlib
import io
import random
import stat
import struct
import warnings
import zipfile

import pytest

from edinburgh_study_agent.nmr_archive import inspect_archive


ROOT = "sample-001/10/"
RAW = b"\x01\x00\x02\x00\x03\x00\x04\x00"
ACQ = b"##TITLE= Synthetic acquisition\n##$NUC1= <1H>\n"


def write_zip(path, members=None, *, compression=zipfile.ZIP_STORED):
    if members is None:
        members = [(ROOT + "fid", RAW), (ROOT + "acqus", ACQ)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, content in members:
                archive.writestr(name, content)
    return path


def inspect(path, **kwargs):
    return inspect_archive(path, "sample-001", "10", **kwargs)


def rejected(path, code, **kwargs):
    with pytest.raises(ValueError) as error:
        inspect(path, **kwargs)
    assert str(error.value) == code
    assert str(path) not in str(error.value)


def test_valid_single_experiment_is_hashed_without_extraction_or_rewriting(tmp_path):
    path = write_zip(tmp_path / "original.zip", [
        ("sample-001/", b""), (ROOT, b""),
        (ROOT + "fid", RAW), (ROOT + "acqus", ACQ),
        (ROOT + "pdata/1/procs", b"##$SI= 1024\n"),
    ], compression=zipfile.ZIP_DEFLATED)
    original = path.read_bytes()
    result = inspect(path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    assert result["format"] == "bruker"
    assert result["member_count"] == 5
    assert result["file_count"] == 3
    assert result["directory_count"] == 2
    assert result["archive_size_bytes"] == len(original)
    assert result["total_uncompressed_bytes"] == len(RAW) + len(ACQ) + 12
    assert result["raw_files"] == ["fid"]
    assert result["acquisition_files"] == ["acqus"]
    assert result["members"] == [
        {"path": "acqus", "size_bytes": len(ACQ), "sha256": hashlib.sha256(ACQ).hexdigest()},
        {"path": "fid", "size_bytes": len(RAW), "sha256": hashlib.sha256(RAW).hexdigest()},
        {"path": "pdata/1/procs", "size_bytes": 12,
         "sha256": hashlib.sha256(b"##$SI= 1024\n").hexdigest()},
    ]
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        assert result["total_compressed_bytes"] == sum(x.compress_size for x in archive.infolist())


def test_multidimensional_raw_data_and_acquisition_files_are_retained(tmp_path):
    path = write_zip(tmp_path / "original.zip", [
        (ROOT + "ser", RAW), (ROOT + "acqus", ACQ),
        (ROOT + "acqu2s", ACQ), (ROOT + "acqu3s", ACQ),
        (ROOT + "title", b"Synthetic data only"),
    ])
    result = inspect(path)
    assert result["raw_files"] == ["ser"]
    assert result["acquisition_files"] == ["acqus", "acqu2s", "acqu3s"]


@pytest.mark.parametrize("member", [
    "/sample-001/10/fid", "C:/sample-001/10/fid", "C:sample-001/10/fid",
    "sample-001\\10\\fid", ROOT + "../fid", ROOT + "./fid", ROOT + "a//fid",
    ROOT + "fid:secret", ROOT + "sub/fid.", ROOT + "sub /fid", ROOT + "NUL",
    ROOT + "sub/CON.txt", ROOT + "bad\x00name", ROOT + "bad\x01name",
])
def test_unsafe_paths_are_rejected(tmp_path, member):
    # ZipInfo itself rewrites backslashes on Windows and strips NULs when
    # writing. Patch both headers to test the actual malicious wire bytes.
    placeholder = "p" * len(member.encode("utf-8"))
    path = write_zip(tmp_path / "unsafe.zip", [(placeholder, RAW), (ROOT + "acqus", ACQ)])
    payload = path.read_bytes()
    assert payload.count(placeholder.encode()) == 2
    path.write_bytes(payload.replace(placeholder.encode(), member.encode("utf-8")))
    rejected(path, "NMR_ARCHIVE_UNSAFE_PATH")


@pytest.mark.parametrize("member", [
    "other-sample/10/fid", "sample-001/11/fid", "sample-001/10-extra/fid",
    "sample-001/acqus", "readme.txt", "other/",
])
def test_other_experiments_and_foreign_entries_are_rejected(tmp_path, member):
    path = write_zip(tmp_path / "mixed.zip", [(ROOT + "fid", RAW),
                    (ROOT + "acqus", ACQ), (member, b"")])
    rejected(path, "NMR_ARCHIVE_EXPERIMENT_MISMATCH")


@pytest.mark.parametrize("additional", [
    [(ROOT + "fid", RAW)], [(ROOT + "FID", RAW)],
    [(ROOT + "Dir/a", b"a"), (ROOT + "dir/b", b"b")],
    [(ROOT + "caf\u00e9/a", b"a"), (ROOT + "cafe\u0301/b", b"b")],
    [(ROOT + "child", b"a"), (ROOT + "child/b", b"b")],
    [(ROOT + "child/", b""), (ROOT + "child", b"a")],
])
def test_duplicate_and_conflicting_paths_are_rejected(tmp_path, additional):
    path = write_zip(tmp_path / "duplicate.zip", [(ROOT + "fid", RAW),
                    (ROOT + "acqus", ACQ)] + additional)
    rejected(path, "NMR_ARCHIVE_DUPLICATE_PATH")


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK])
def test_symlinks_and_special_entries_are_rejected(tmp_path, mode):
    entry = zipfile.ZipInfo(ROOT + "danger")
    entry.create_system = 3
    entry.external_attr = (mode | 0o600) << 16
    path = write_zip(tmp_path / "special.zip", [(ROOT + "fid", RAW),
                    (ROOT + "acqus", ACQ), (entry, b"target")])
    rejected(path, "NMR_ARCHIVE_UNSUPPORTED_ENTRY")


def test_encrypted_flag_is_rejected_before_member_read(tmp_path):
    path = write_zip(tmp_path / "encrypted.zip")
    payload = bytearray(path.read_bytes())
    for signature, flag_offset in [(b"PK\x03\x04", 6), (b"PK\x01\x02", 8)]:
        position = 0
        while (position := payload.find(signature, position)) != -1:
            struct.pack_into("<H", payload, position + flag_offset, 1)
            position += len(signature)
    path.write_bytes(payload)
    rejected(path, "NMR_ARCHIVE_ENCRYPTED")


@pytest.mark.parametrize("members,code", [
    ([], "NMR_ARCHIVE_EMPTY"),
    ([(ROOT, b"")], "NMR_ARCHIVE_MISSING_RAW_DATA"),
    ([(ROOT + "fid", b""), (ROOT + "acqus", ACQ)], "NMR_ARCHIVE_MISSING_RAW_DATA"),
    ([(ROOT + "pdata/1/fid", RAW), (ROOT + "acqus", ACQ)], "NMR_ARCHIVE_MISSING_RAW_DATA"),
    ([(ROOT + "fid", RAW)], "NMR_ARCHIVE_MISSING_ACQUISITION"),
    ([(ROOT + "fid", RAW), (ROOT + "acqus", b"")], "NMR_ARCHIVE_MISSING_ACQUISITION"),
    ([(ROOT + "fid", RAW), (ROOT + "pdata/1/acqus", ACQ)], "NMR_ARCHIVE_MISSING_ACQUISITION"),
])
def test_missing_root_raw_or_acquisition_data_is_rejected(tmp_path, members, code):
    rejected(write_zip(tmp_path / "incomplete.zip", members), code)


def test_zero_length_fid_does_not_hide_valid_ser(tmp_path):
    path = write_zip(tmp_path / "ser.zip", [(ROOT + "fid", b""),
                    (ROOT + "ser", RAW), (ROOT + "acqus", ACQ)])
    assert inspect(path)["raw_files"] == ["ser"]


def test_uncompressed_size_is_bounded_per_member_and_total(tmp_path):
    path = write_zip(tmp_path / "limit.zip")
    rejected(path, "NMR_ARCHIVE_SIZE_LIMIT", max_uncompressed_bytes=len(ACQ) - 1)
    rejected(path, "NMR_ARCHIVE_SIZE_LIMIT", max_uncompressed_bytes=len(ACQ) + len(RAW) - 1)
    assert inspect(path, max_uncompressed_bytes=len(ACQ) + len(RAW))["file_count"] == 2


def test_member_count_and_path_length_are_bounded(tmp_path):
    members = [(ROOT + "fid", RAW), (ROOT + "acqus", ACQ)]
    members += [(ROOT + f"extra/{i}", b"") for i in range(1999)]
    rejected(write_zip(tmp_path / "many.zip", members), "NMR_ARCHIVE_MEMBER_LIMIT")
    path = write_zip(tmp_path / "long.zip", [(ROOT + "x" * 1024, RAW), (ROOT + "acqus", ACQ)])
    rejected(path, "NMR_ARCHIVE_UNSAFE_PATH")


def test_forged_directory_count_cannot_bypass_the_allocation_bound(tmp_path):
    members = [(ROOT + "fid", RAW), (ROOT + "acqus", ACQ)]
    members += [(ROOT + f"extra/{i}", b"") for i in range(1999)]
    path = write_zip(tmp_path / "forged-count.zip", members)
    payload = bytearray(path.read_bytes())
    end = payload.rindex(b"PK\x05\x06")
    struct.pack_into("<2H", payload, end + 8, 1, 1)
    path.write_bytes(payload)
    rejected(path, "NMR_ARCHIVE_MEMBER_LIMIT")


def test_member_data_is_streamed_in_bounded_chunks(tmp_path, monkeypatch):
    raw = random.Random(42).randbytes(300_000)
    path = write_zip(tmp_path / "stream.zip", [(ROOT + "fid", raw), (ROOT + "acqus", ACQ)],
                     compression=zipfile.ZIP_DEFLATED)
    read_sizes = []
    original_read = zipfile.ZipExtFile.read

    def read(member, size=-1):
        read_sizes.append(size)
        assert 0 < size <= 64 * 1024
        return original_read(member, size)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", read)
    result = inspect(path)
    assert len(read_sizes) >= 7
    record = next(member for member in result["members"] if member["path"] == "fid")
    assert record["sha256"] == hashlib.sha256(raw).hexdigest()
    assert record["size_bytes"] == len(raw)


def test_suspicious_compression_ratio_is_rejected_without_decompression(tmp_path):
    path = write_zip(tmp_path / "ratio.zip", [(ROOT + "fid", b"\x00" * 1024 * 1024),
                    (ROOT + "acqus", ACQ)], compression=zipfile.ZIP_DEFLATED)
    rejected(path, "NMR_ARCHIVE_COMPRESSION_RATIO")


def test_unsupported_compression_is_rejected(tmp_path):
    rejected(write_zip(tmp_path / "bzip.zip", compression=zipfile.ZIP_BZIP2),
             "NMR_ARCHIVE_UNSUPPORTED_COMPRESSION")


@pytest.mark.parametrize("payload", [b"", b"<html>Login required</html>", b"PK\x03\x04\x00\x00"])
def test_non_zip_and_truncated_data_are_rejected(tmp_path, payload):
    path = tmp_path / "private-location.zip"
    path.write_bytes(payload)
    rejected(path, "NMR_ARCHIVE_INVALID_ZIP")


def test_crc_corruption_is_detected_and_original_bytes_are_unchanged(tmp_path):
    path = write_zip(tmp_path / "corrupt.zip")
    payload = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(ROOT + "fid")
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    payload[offset] ^= 0xFF
    path.write_bytes(payload)
    rejected(path, "NMR_ARCHIVE_INTEGRITY_ERROR")
    assert path.read_bytes() == payload


def test_directory_crc_and_local_header_are_validated_too(tmp_path):
    path = write_zip(tmp_path / "directory-corrupt.zip", [
        (ROOT, b""), (ROOT + "fid", RAW), (ROOT + "acqus", ACQ),
    ])
    payload = bytearray(path.read_bytes())
    central = payload.index(b"PK\x01\x02")
    struct.pack_into("<I", payload, central + 16, 12345)
    path.write_bytes(payload)
    rejected(path, "NMR_ARCHIVE_INTEGRITY_ERROR")


def test_truncated_central_directory_is_rejected(tmp_path):
    path = write_zip(tmp_path / "truncated.zip")
    path.write_bytes(path.read_bytes()[:-18])
    rejected(path, "NMR_ARCHIVE_INVALID_ZIP")


def test_missing_file_error_does_not_expose_private_path(tmp_path):
    rejected(tmp_path / "student-account-private.zip", "NMR_ARCHIVE_UNREADABLE")


@pytest.mark.parametrize("budget", [0, -1, True, 1.5, "100"])
def test_invalid_budgets_fail_before_open(tmp_path, budget):
    rejected(tmp_path / "not-opened.zip", "NMR_ARCHIVE_ARGUMENT_INVALID", max_uncompressed_bytes=budget)


@pytest.mark.parametrize("dataset,experiment", [
    ("../sample", "10"), ("sample/other", "10"), ("sample", "../10"),
    ("", "10"), ("sample", ""), ("sample", 10), ("NUL", "10"),
])
def test_invalid_expected_root_fails_before_open(tmp_path, dataset, experiment):
    with pytest.raises(ValueError, match="^NMR_ARCHIVE_ARGUMENT_INVALID$"):
        inspect_archive(tmp_path / "not-opened.zip", dataset, experiment)
