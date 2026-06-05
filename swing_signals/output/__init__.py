"""Alert / output layer (research file 12).

An ``Alerter`` interface with interchangeable backends (Telegram primary, email
backup) plus a daily report formatter. A separate failure path alerts on
exceptions so a silent failure never hides a missing signal. Backends land in
Stage 6.
"""
