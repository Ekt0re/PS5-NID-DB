from nid_db.nid import compute_nid, strip_nid_postfix, NID_RE

EMULATORS = ("anyps5", "kyty", "sharpemu")
STATUSES = ("implemented", "stub", "unknown", "not_implemented")

__all__ = ["EMULATORS", "STATUSES", "compute_nid", "strip_nid_postfix", "NID_RE"]
