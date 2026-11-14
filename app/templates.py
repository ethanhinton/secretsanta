"""Composing the draw-notification email (HTML + plain-text alternative)."""
from __future__ import annotations

import html

from .models import DrawSettings


def build_email(to_name: str, drawn_name: str, settings: DrawSettings):
    """Return (subject, html, plain_text)."""
    to_name = html.escape(to_name)
    drawn_name = html.escape(drawn_name)
    notes = html.escape(settings.notes.strip())
    spend = settings.max_spend.strip()
    currency = html.escape(settings.currency)

    spend_line = ""
    spend_text = ""
    if spend:
        spend_line = (
            f"<p>The maximum spend is <b>{currency}{html.escape(spend)}</b> "
            f"so please keep within this limit!</p>"
        )
        spend_text = f"The maximum spend is {settings.currency}{spend} so please keep within this limit!\n"

    notes_block = f"<p>{notes}</p>" if notes else ""
    notes_text = f"{settings.notes.strip()}\n" if notes else ""

    subject = settings.subject.strip() or "Secret Santa draw!"

    html_body = f"""<html>
    <head></head>
    <body>
        <p>Hello {to_name}!</p>
        <p>The time has come to get into the Christmas spirit and draw names for the house Secret Santa!</p>
        {spend_line}
        <p>You have drawn <b>{drawn_name}</b>.</p>
        {notes_block}
        <p>Let the elfing <b>BEGIN!</b></p>
    </body>
    </html>
    """

    text_body = (
        f"Hello {to_name}!\n\n"
        f"The time has come to get into the Christmas spirit and draw names for the house Secret Santa!\n\n"
        f"{spend_text}"
        f"You have drawn {drawn_name}.\n"
        f"{notes_text}"
        f"\nLet the elfing BEGIN!"
    )

    return subject, html_body, text_body
