"""Generate printable QR badge PNGs for every active employee → ../badges/.

Run from backend/:  python make_badges.py
The kiosk/scanner reads these; each encodes the employee's attendance token.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")

from app.database import SessionLocal
from app.models import QRToken, User
from app.utils.qr import make_qr_png

OUT = os.path.join(os.path.dirname(__file__), "..", "badges")


def run() -> None:
    os.makedirs(OUT, exist_ok=True)
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active.is_(True)).all()
        for u in users:
            tok = db.query(QRToken).filter(QRToken.user_id == u.id, QRToken.is_active.is_(True)).first()
            if not tok:
                continue
            safe = u.email.split("@")[0]
            path = os.path.join(OUT, f"badge-{safe}.png")
            with open(path, "wb") as fh:
                fh.write(make_qr_png(tok.token))
            print(f"  {u.name:<16} -> badges/badge-{safe}.png")
        print(f"\n{len(users)} badges written to {os.path.abspath(OUT)}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
