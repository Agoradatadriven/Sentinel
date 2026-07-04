"""QR code generation for employee attendance badges.

Each active employee has a ``qr_tokens`` row; the kiosk camera reads the token string and the
backend maps it back to the user. ``make_qr_png`` renders that token as a scannable PNG.
"""
from __future__ import annotations

import io
import secrets

import qrcode


def new_token() -> str:
    """A URL-safe random token for a new QR badge."""
    return secrets.token_urlsafe(18)


def make_qr_png(data: str, box_size: int = 10, border: int = 3) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    # Agora graphite on white — matches the badge print aesthetic.
    img = qr.make_image(fill_color="#1A1B1E", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
