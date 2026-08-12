from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from shutil import which
from typing import Any

from PIL import Image


RASTER_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
OFFICE_METAFILE_EXTENSIONS = {".wmf", ".emf"}


class PandocAdapter:
    """Converts documents to Markdown and extracts media without task knowledge."""

    def __init__(self, executable: str = "pandoc") -> None:
        self._executable = executable

    def is_available(self) -> bool:
        return which(self._executable) is not None or self._markitdown_available()

    @staticmethod
    def _markitdown_available() -> bool:
        try:
            import markitdown  # noqa: F401
        except ImportError:
            return False
        return True

    def convert(self, source_path: str, target_format: str, output_path: str | None = None) -> dict[str, str]:
        if which(self._executable) is None:
            return self._markitdown_convert(source_path, target_format, output_path)

        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        target = Path(output_path) if output_path else source.with_suffix(
            {"markdown": ".md", "html": ".html", "plain": ".txt"}[target_format]
        )
        subprocess.run([self._executable, str(source), "-o", str(target)], check=True, capture_output=True, text=True)
        return {
            "source_path": str(source),
            "output_path": str(target),
            "target_format": target_format,
            "text": self._read_output_text(target),
        }

    def unpack_to_markdown(self, source_path: str, markdown_path: str, media_dir: str) -> dict[str, Any]:
        if which(self._executable) is None:
            return self._markitdown_unpack_to_markdown(source_path, markdown_path, media_dir)

        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        target = Path(markdown_path)
        media = Path(media_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        media.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [self._executable, str(source), "-t", "markdown", "-o", str(target), f"--extract-media={media}"],
            check=True,
            capture_output=True,
            text=True,
        )
        text = self._read_output_text(target)
        text, converted_metafiles, conversion_warnings = self._convert_office_metafiles(text, media)
        if converted_metafiles:
            target.write_text(text, encoding="utf-8")
        images = [
            path
            for path in sorted(media.rglob("*"))
            if path.is_file() and path.suffix.lower() in RASTER_IMAGE_EXTENSIONS
        ]
        return {
            "source_path": str(source),
            "output_path": str(target),
            "media_dir": str(media),
            "image_count": len(images),
            "images": [str(path) for path in images],
            "text": text,
            "converted_metafile_count": converted_metafiles,
            "warnings": conversion_warnings,
        }

    def _markitdown_convert(self, source_path: str, target_format: str, output_path: str | None) -> dict[str, str]:
        if not self._markitdown_available():
            raise RuntimeError("Neither pandoc nor the MarkItDown fallback is available")
        if target_format not in {"markdown", "plain"}:
            raise RuntimeError("MarkItDown fallback supports Markdown or plain-text conversion only")
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        target = Path(output_path) if output_path else source.with_suffix(".md" if target_format == "markdown" else ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        from markitdown import MarkItDown

        converted = MarkItDown(enable_plugins=False).convert(str(source))
        text = str(getattr(converted, "text_content", ""))
        target.write_text(text, encoding="utf-8")
        return {"source_path": str(source), "output_path": str(target), "target_format": target_format, "text": text}

    def _markitdown_unpack_to_markdown(self, source_path: str, markdown_path: str, media_dir: str) -> dict[str, Any]:
        """Fallback that retains DOCX images for human review without guessing anchors."""
        result = self._markitdown_convert(source_path, "markdown", markdown_path)
        source = Path(source_path)
        media = Path(media_dir)
        media.mkdir(parents=True, exist_ok=True)
        images: list[Path] = []
        if source.suffix.lower() == ".docx":
            with zipfile.ZipFile(source) as archive:
                for member in archive.namelist():
                    if not member.startswith("word/media/") or member.endswith("/"):
                        continue
                    target = media / Path(member).name
                    target.write_bytes(archive.read(member))
                    images.append(target)
            rewritten = self._rewrite_markitdown_docx_images(source, str(result.get("text") or ""))
            rewritten, converted_metafiles, conversion_warnings = self._convert_office_metafiles(rewritten, media)
            Path(markdown_path).write_text(rewritten, encoding="utf-8")
            result["text"] = rewritten
        else:
            converted_metafiles = 0
            conversion_warnings = []
        images = [
            path
            for path in sorted(media.rglob("*"))
            if path.is_file() and path.suffix.lower() in RASTER_IMAGE_EXTENSIONS
        ]
        return {
            **result,
            "media_dir": str(media),
            "image_count": len(images),
            "images": [str(path) for path in images],
            "conversion_engine": "markitdown_fallback",
            "warning": "Pandoc is unavailable. Images were preserved for review but require confirmation before question binding.",
            "converted_metafile_count": converted_metafiles,
            "warnings": conversion_warnings,
        }

    @classmethod
    def _convert_office_metafiles(cls, markdown: str, media_dir: Path) -> tuple[str, int, list[str]]:
        """Rasterize browser-incompatible Word metafiles and rewrite Markdown paths."""
        converted = 0
        warnings: list[str] = []
        for source in sorted(media_dir.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in OFFICE_METAFILE_EXTENSIONS:
                continue
            target = cls._available_png_path(source)
            try:
                cls._render_metafile_png(source, target)
            except Exception as exc:  # noqa: BLE001
                target.unlink(missing_ok=True)
                warnings.append(f"{source.name} 转 PNG 失败：{exc}")
                continue

            markdown = cls._rewrite_media_reference(markdown, source, target)
            source.unlink(missing_ok=True)
            converted += 1
        return markdown, converted, warnings

    @staticmethod
    def _available_png_path(source: Path) -> Path:
        target = source.with_suffix(".png")
        if not target.exists():
            return target
        target = source.with_name(f"{source.stem}-metafile.png")
        index = 2
        while target.exists():
            target = source.with_name(f"{source.stem}-metafile-{index}.png")
            index += 1
        return target

    @staticmethod
    def _render_metafile_png(source: Path, target: Path, target_size: int = 1600) -> None:
        # Pillow reports the metafile's logical canvas before rendering, which is
        # not the pixel size produced at a given DPI. Probe at 72 DPI first so
        # small Word drawings are not accidentally rasterized as tiny previews.
        with Image.open(source) as probe:
            try:
                probe.load(dpi=72)
            except TypeError:
                probe.load()
            base_size = max(int(probe.width or 1), int(probe.height or 1), 1)

        dpi = min(1200, max(72, round(72 * target_size / base_size)))
        with Image.open(source) as raw_image:
            try:
                raw_image.load(dpi=dpi)
            except TypeError:
                raw_image.load()
            image = raw_image.convert("RGBA" if "A" in raw_image.getbands() else "RGB")
            image.save(target, "PNG", optimize=True)

    @staticmethod
    def _rewrite_media_reference(markdown: str, source: Path, target: Path) -> str:
        replacements = {
            str(source): str(target),
            source.as_posix(): target.as_posix(),
            source.name: target.name,
        }
        for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            markdown = markdown.replace(old, new)
        return markdown

    @staticmethod
    def _rewrite_markitdown_docx_images(source: Path, markdown: str) -> str:
        """Replace MarkItDown data-URI placeholders with extracted DOCX media names."""
        try:
            with zipfile.ZipFile(source) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
                relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        except (KeyError, OSError, ET.ParseError, zipfile.BadZipFile):
            return markdown

        embed_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
        rid_to_filename = {
            str(node.attrib.get("Id") or ""): Path(str(node.attrib.get("Target") or "").replace("\\", "/")).name
            for node in relationships
            if str(node.attrib.get("Type") or "").endswith("/image")
        }
        drawing_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
        doc_pr_tag = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
        blip_tag = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
        by_alt: dict[str, str] = {}
        ordered_filenames: list[str] = []
        for drawing in document.iter(drawing_tag):
            doc_pr = next(drawing.iter(doc_pr_tag), None)
            blip = next(drawing.iter(blip_tag), None)
            if blip is None:
                continue
            filename = rid_to_filename.get(str(blip.attrib.get(embed_key) or ""))
            if not filename:
                continue
            ordered_filenames.append(filename)
            if doc_pr is not None:
                for key in ("descr", "title", "name"):
                    alt = str(doc_pr.attrib.get(key) or "").strip()
                    if alt:
                        by_alt.setdefault(alt, filename)
        if not ordered_filenames:
            return markdown

        data_image = re.compile(r"!\[([^\]]*)\]\(data:image/[^)]*\)(?:\{[^}]*\})?", re.IGNORECASE)
        image_index = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal image_index
            alt = match.group(1).strip()
            filename = by_alt.get(alt)
            if filename is None and image_index < len(ordered_filenames):
                filename = ordered_filenames[image_index]
            image_index += 1
            return match.group(0) if not filename else f"![{alt}]({filename})"

        return data_image.sub(replace, markdown)

    @staticmethod
    def _read_output_text(target: Path) -> str:
        if not target.exists():
            return ""
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                return target.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        try:
            return target.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return ""
