from __future__ import annotations

from typing import cast

from jacaranda_api.pipeline.models import JsonDict

# Per-upload budget for what is fed to S1; the full parsed document stays in
# the database, this only bounds the extraction prompt input.
MAX_CHARS_PER_UPLOAD = 6000
MAX_BLOCKS_PER_UPLOAD = 12


def merge_upload_evidence(
    evidence: JsonDict, uploads: list[JsonDict]
) -> tuple[JsonDict, list[JsonDict]]:
    """Append uploaded documents to the evidence pack as user_upload sources and
    return the extraction chunks for them.

    Sources continue the pack's SRC numbering; every chunk's url_or_document is
    ``upload://{upload_id}#<locator>`` so extracted candidates stay traceable to
    a page/paragraph/sheet. Uploads are secondary-tier evidence: they are files
    supplied by members, not documents fetched from the official channel.
    """
    if not uploads:
        return evidence, []
    sources = [dict(source) for source in cast(list[JsonDict], evidence["sources"])]
    warnings = [*cast(list[str], evidence["warnings"])]
    next_number = (
        max(int(str(source["source_id"]).removeprefix("SRC-")) for source in sources) + 1
    )
    chunks: list[JsonDict] = []
    for upload in uploads:
        source_id = f"SRC-{next_number:03d}"
        next_number += 1
        retrieved_at = str(upload["created_at"])
        sources.append(
            {
                "source_id": source_id,
                "type": "user_upload",
                "title": str(upload["filename"]),
                "url_or_document": f"upload://{upload['upload_id']}",
                "retrieved_at": retrieved_at,
                "reliability_tier": "secondary",
                "language": "zh",
            }
        )
        used_chars = 0
        used_blocks = 0
        truncated = False
        for block in cast(list[JsonDict], upload["blocks"]):
            text = str(block["text"])
            if used_blocks >= MAX_BLOCKS_PER_UPLOAD or used_chars + len(text) > (
                MAX_CHARS_PER_UPLOAD
            ):
                truncated = True
                break
            chunks.append(
                {
                    "source_id": source_id,
                    "type": "user_upload",
                    "locator": str(block["locator"]),
                    "published_date": None,
                    "retrieved_at": retrieved_at,
                    "url_or_document": f"upload://{upload['upload_id']}#{block['locator']}",
                    "language": "zh",
                    "text": text,
                }
            )
            used_chars += len(text)
            used_blocks += 1
        if truncated:
            warnings.append(
                f"upload {upload['filename']} truncated for extraction "
                f"({used_blocks} blocks / {used_chars} chars used)"
            )
    merged = {**evidence, "sources": sources, "warnings": warnings}
    return merged, chunks
