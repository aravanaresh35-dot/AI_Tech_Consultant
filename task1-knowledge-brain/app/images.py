"""Image handling. We only claim an image was 'analyzed' if a vision model really described it."""
from __future__ import annotations

import base64
import logging

from tech_common.ai import AIClient, AIUnavailable

from .fetcher import Fetcher, FetchError

logger = logging.getLogger("images")
SUPPORTED = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PROMPT_VERSION = "image-desc-v1"


def process_images(images: list[dict], fetcher: Fetcher, ai: AIClient, enabled: bool, max_bytes: int) -> list[dict]:
    out = []
    for im in images:
        rec = dict(im)
        if not enabled:
            rec.update(analysis_status="not_analyzed",
                       analysis_note="Image analysis disabled (ANALYZE_IMAGES=false); URL, alt text and caption preserved.")
        elif not ai.is_live:
            rec.update(analysis_status="not_analyzed",
                       analysis_note="No live vision model configured (demo mode); URL, alt text and caption preserved.")
        else:
            try:
                data, ctype = fetcher.get_bytes(im["url"], max_bytes)
                ctype = ctype.split(";")[0].strip()
                if ctype not in SUPPORTED:
                    raise FetchError(f"Unsupported image type {ctype}")
                block = {"type": "image", "source": {"type": "base64", "media_type": ctype,
                                                     "data": base64.b64encode(data).decode()}}
                res = ai.generate(
                    "Describe this support-article screenshot factually in 1-3 sentences. Mention visible UI labels. "
                    "Do not guess beyond what is visible.",
                    [block, {"type": "text", "text": f"Alt text: {im.get('alt')}. Caption: {im.get('caption')}"}],
                    PROMPT_VERSION, max_tokens=300)
                rec.update(analysis=res.text.strip(), analysis_status="analyzed", analysis_note=f"model={res.model}")
            except (FetchError, AIUnavailable) as exc:  # an image failure must never lose the article
                logger.warning("image failed: %s", exc)
                rec.update(analysis_status="failed", analysis_note=str(exc)[:200])
        out.append(rec)
    return out
