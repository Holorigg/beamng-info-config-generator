"""
Read and write files inside ZIP archives without extraction.
"""
import os
import copy
import io
import time
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path

import json_utils
from storage import backup_file, check_cancel


def scan_zip(zip_path: Path, issues=None, cancel=None) -> list:
    """
    Scan a zip for .pc configs and their info_config json files.
    Returns list of ConfigEntry objects (imported locally to avoid circular import).
    """
    from scanner import ConfigEntry, MAX_METADATA_BYTES
    from parser import parse_pc
    from generator import validate

    entries = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names_set = set(zf.namelist())

            pc_files = [
                n for n in names_set
                if n.lower().endswith(".pc") and ".bak." not in n.lower()
            ]

            def read_metadata(name):
                if zf.getinfo(name).file_size > MAX_METADATA_BYTES:
                    raise ValueError("File exceeds the 16 MiB metadata limit")
                return zf.read(name)

            for pc_zip_path in sorted(pc_files):
                check_cancel(cancel)
                config_name = Path(pc_zip_path).stem
                pc_dir      = Path(pc_zip_path).parent  # keep as Path to avoid "./" prefix

                def _zp(filename: str) -> str:
                    """Build a zip-safe path (no leading './')."""
                    p = (pc_dir / filename).as_posix()
                    return p.lstrip("./") if p.startswith("./") else p

                names = [
                    f"info_{config_name}.json",
                    f"info_config_{config_name}.json",
                ]
                if config_name.lower().startswith("config_"):
                    stripped = config_name[len("config_"):]
                    names += [f"info_config_{stripped}.json", f"info_{stripped}.json"]

                candidates = [_zp(n) for n in names]
                info_zip_path = next((c for c in candidates if c in names_set), candidates[0])

                try:
                    pc_content = json_utils.load_bytes(read_metadata(pc_zip_path))
                except Exception as exc:
                    if issues is not None:
                        issues.append(f"{zip_path}!{pc_zip_path}: {exc}")
                    continue

                auto = parse_pc(pc_content)

                thumbnail_path = None
                for ext in ('.jpg', '.jpeg', '.png'):
                    img_zip_path = _zp(f"{config_name}{ext}")
                    if img_zip_path in names_set:
                        thumbnail_path = img_zip_path
                        break

                if info_zip_path in names_set:
                    info_raw = None
                    parse_error = None
                    try:
                        info_raw = json_utils.decode(read_metadata(info_zip_path))
                        info_content = json_utils.loads(info_raw)
                    except Exception as exc:
                        parse_error = str(exc)
                        if issues is not None:
                            issues.append(f"{zip_path}!{info_zip_path}: {exc}")
                        info_content = {}
                    missing = validate(info_content)
                    status  = "ok" if not missing else "bad"
                else:
                    info_raw     = None
                    info_content = None
                    missing      = []
                    status       = "missing"
                    parse_error  = None

                entries.append(ConfigEntry(
                    pc_path=pc_zip_path,
                    info_path=info_zip_path if info_content is not None else None,
                    status=status,
                    source="zip",
                    source_path=str(zip_path),
                    pc_content={},
                    info_content=info_content,
                    info_raw=info_raw,
                    missing_fields=missing,
                    config_name=config_name,
                    auto_detected=auto,
                    thumbnail_path=thumbnail_path,
                    parse_error=parse_error,
                ))

    except (zipfile.BadZipFile, OSError) as exc:
        if issues is not None:
            issues.append(f"{zip_path}: {exc}")

    return entries


def _zip_path(name: str) -> str:
    """Normalize a path for ZIP storage."""
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    if not name or name.startswith("/") or any(p in ("", "..") for p in name.split("/")) or ":" in name:
        raise ValueError(f"Invalid archive path: {name}")
    return name


_LOCAL_HEADER = struct.Struct("<4s5H3L2H")
_LOCAL_SIGNATURE = b"PK\x03\x04"
_DESCRIPTOR_SIGNATURE = 0x08074B50
_ZIP64_EXTRA = 0x0001
_DATA_DESCRIPTOR = 0x08


def _strip_zip64_extra(extra: bytes) -> bytes:
    """Drop ZIP64 size fields; the writer adds its own when they are needed."""
    kept, position = [], 0
    while position + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, position)
        end = position + 4 + size
        if tag != _ZIP64_EXTRA:
            kept.append(extra[position:end])
        position = end
    kept.append(extra[position:])
    return b"".join(kept)


def _copy_raw_entry(source, dst, info, cancel=None, advance=None):
    """Copy one member's compressed bytes as they are, without recompressing."""
    source.seek(info.header_offset)
    header = source.read(_LOCAL_HEADER.size)
    if len(header) != _LOCAL_HEADER.size or header[:4] != _LOCAL_SIGNATURE:
        raise zipfile.BadZipFile(f"Bad local header: {info.filename}")
    name_length, extra_length = _LOCAL_HEADER.unpack(header)[-2:]
    source.seek(name_length + extra_length, os.SEEK_CUR)

    new_info = copy.copy(info)
    new_info.extra = _strip_zip64_extra(info.extra)
    zip64 = info.file_size > zipfile.ZIP64_LIMIT or info.compress_size > zipfile.ZIP64_LIMIT
    output = dst.fp
    output.seek(dst.start_dir)
    new_info.header_offset = output.tell()
    output.write(new_info.FileHeader(zip64))
    remaining = info.compress_size
    while remaining:
        check_cancel(cancel)
        chunk = source.read(min(remaining, 1024 * 1024))
        if not chunk:
            raise zipfile.BadZipFile(f"Truncated member: {info.filename}")
        output.write(chunk)
        remaining -= len(chunk)
        if advance:
            advance(len(chunk), info.filename)
    if new_info.flag_bits & _DATA_DESCRIPTOR:
        layout = "<LLQQ" if zip64 else "<LLLL"
        output.write(struct.pack(layout, _DESCRIPTOR_SIGNATURE, info.CRC, info.compress_size, info.file_size))
    dst.start_dir = output.tell()
    dst.filelist.append(new_info)
    dst.NameToInfo[new_info.filename] = new_info


def _append_or_shadow(zip_path, normalized, directory_offset, cancel=None):
    """
    Write members after the last entry and point the central directory at them.

    A replaced member's old bytes stay in the file but are no longer listed, so
    the archive is never rewritten. On any failure the original central
    directory is put back and the file is truncated to its original size.
    """
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as tail:
        with zip_path.open("rb") as original:
            original.seek(directory_offset)
            shutil.copyfileobj(original, tail, length=1024 * 1024)
        try:
            with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
                replaced = [name for name in normalized if name in zf.NameToInfo]
                if replaced:
                    previous = {name: zf.getinfo(name) for name in replaced}
                    zf.filelist = [info for info in zf.filelist if info.filename not in previous]
                    for name in replaced:
                        del zf.NameToInfo[name]
                for name, data in normalized.items():
                    check_cancel(cancel)
                    if name in replaced:
                        info = copy.copy(previous[name])
                        info.extra = _strip_zip64_extra(info.extra)
                        info.flag_bits &= ~_DATA_DESCRIPTOR
                        info.compress_type = zipfile.ZIP_DEFLATED
                        zf.writestr(info, data)
                    else:
                        zf.writestr(name, data)
                check_cancel(cancel)
        except BaseException:
            tail.seek(0)
            with zip_path.open("r+b") as original:
                original.seek(directory_offset)
                shutil.copyfileobj(tail, original, length=1024 * 1024)
                original.truncate()
                original.flush()
                os.fsync(original.fileno())
            raise


def write_many_to_zip(zip_path: str | Path, updates: dict[str, str],
                      mode="auto", backup=False, cancel=None, progress=None):
    """
    Add or replace many files inside a zip archive.

    "auto" writes new and changed members at the end of the archive and only
    rewrites its central directory, so the time does not depend on the mod's
    size. "disk" and "ram" rebuild the whole archive without the stale copies,
    moving compressed data as it is. progress(done_bytes, total_bytes, name)
    reports a rebuild.
    """
    zip_path = Path(zip_path)
    if mode not in ("auto", "disk", "ram"):
        raise ValueError("Unknown ZIP write mode")
    normalized = {}
    for name, text in updates.items():
        target = _zip_path(name)
        if target in normalized:
            raise ValueError(f"Duplicate update path: {target}")
        normalized[target] = text.encode("utf-8")
    if not normalized:
        return

    check_cancel(cancel)
    exists = zip_path.exists()
    directory_offset = 0
    existing_names = set()
    if exists:
        with zipfile.ZipFile(zip_path, "r") as zf:
            existing_names = set(zf.namelist())
            # zipfile's append writer overwrites the directory at start_dir.
            directory_offset = zf.start_dir
    if backup and exists:
        backup_file(zip_path)

    if exists and mode == "auto":
        _append_or_shadow(zip_path, normalized, directory_offset, cancel)
        return

    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{zip_path.stem}.",
            suffix=".tmp.zip",
            dir=str(zip_path.parent),
        )
        os.close(fd)

        ram_buffer = io.BytesIO() if mode == "ram" else None
        destination = ram_buffer if ram_buffer is not None else temp_name
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            if exists:
                with zipfile.ZipFile(zip_path, "r") as src, zip_path.open("rb") as raw:
                    dst.comment = src.comment
                    # Only the last copy of a duplicated name is kept, as zipfile reads it.
                    kept = [info for info in src.infolist()
                            if info.filename not in normalized and src.getinfo(info.filename) is info]
                    total = sum(info.compress_size for info in kept) or 1
                    state = {"done": 0, "last": 0.0}

                    def advance(count, name):
                        state["done"] += count
                        now = time.monotonic()
                        if progress and now - state["last"] >= 0.05:
                            progress(state["done"], total, name)
                            state["last"] = now

                    for info in kept:
                        check_cancel(cancel)
                        _copy_raw_entry(raw, dst, info, cancel, advance)
                    if progress:
                        progress(total, total, "")
                    for name, data in normalized.items():
                        check_cancel(cancel)
                        if name in existing_names:
                            info = copy.copy(src.getinfo(name))
                            info.extra = _strip_zip64_extra(info.extra)
                            info.flag_bits &= ~_DATA_DESCRIPTOR
                            info.compress_type = zipfile.ZIP_DEFLATED
                            dst.writestr(info, data)
                        else:
                            dst.writestr(name, data)
            else:
                for name, data in normalized.items():
                    check_cancel(cancel)
                    dst.writestr(name, data)
        if ram_buffer is not None:
            ram_buffer.seek(0)
            with open(temp_name, "wb") as stream:
                shutil.copyfileobj(ram_buffer, stream, length=1024 * 1024)
            ram_buffer.close()
        check_cancel(cancel)
        with open(temp_name, "r+b") as stream:
            os.fsync(stream.fileno())
        if exists:
            shutil.copymode(zip_path, temp_name)
        os.replace(temp_name, zip_path)
        temp_name = None
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink(missing_ok=True)


def write_to_zip(zip_path: str, target_path_in_zip: str, content: str):
    """Backward-compatible single-file wrapper."""
    write_many_to_zip(zip_path, {target_path_in_zip: content})
