from nid_db.scanners.anyps5 import scan_anyps5
from nid_db.scanners.kyty import scan_kyty
from nid_db.scanners.sharpemu import scan_sharpemu

SCANNERS = {
    "anyps5": scan_anyps5,
    "kyty": scan_kyty,
    "sharpemu": scan_sharpemu,
}

__all__ = ["SCANNERS", "scan_anyps5", "scan_kyty", "scan_sharpemu"]
