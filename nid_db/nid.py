import re
from base64 import b64encode
from hashlib import sha1

SUFFIX = bytes(
    [0x51, 0x8D, 0x64, 0xA6, 0x35, 0xDE, 0xD8, 0xC1, 0xE6, 0xB0, 0x39, 0xB1, 0xC3, 0xE5, 0x52, 0x30]
)
NID_POSTFIX = "_nid_postfix"
NID_RE = re.compile(r"^[A-Za-z0-9+\-]{11}$")


def compute_nid(symbol: str) -> str:
    digest = sha1(symbol.encode() + SUFFIX).digest()
    return b64encode(digest[:8][::-1], altchars=b"+-").decode("ascii").rstrip("=")


def strip_nid_postfix(name: str) -> str:
    return re.sub(r"_nid_disambig[0-9]+$", "", name.removesuffix(NID_POSTFIX))
