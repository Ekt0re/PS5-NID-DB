import tempfile
import unittest
from pathlib import Path

from nid_db import compute_nid
from nid_db.classify import classify_cpp, classify_csharp
from nid_db.merge import merge_records, pick_name
from nid_db.scanners.anyps5 import scan_anyps5
from nid_db.scanners.kyty import scan_kyty
from nid_db.scanners.sharpemu import scan_sharpemu


class TestComputeNid(unittest.TestCase):
    def test_known_nid(self):
        self.assertEqual(compute_nid("sceAjmMemoryUnregister"), "pIpGiaYkHkM")

    def test_deterministic(self):
        self.assertEqual(compute_nid("sceKernelPollEvent"), compute_nid("sceKernelPollEvent"))
        self.assertEqual(len(compute_nid("sceKernelPollEvent")), 11)


class TestClassifyCpp(unittest.TestCase):
    def test_const_return_is_stub(self):
        body = "{ (void)context; (void)ptr; return 0; }"
        self.assertEqual(classify_cpp(body), "stub")

    def test_not_implemented_marker(self):
        body = "{ NotImplemented_nid_no_patch(\"x\"); return 0; }"
        self.assertEqual(classify_cpp(body), "stub")

    def test_real_logic(self):
        body = "{ if (ptr == nullptr) return -1; ctx->doThing(ptr); return 0; }"
        self.assertEqual(classify_cpp(body), "implemented")

    def test_empty_body(self):
        self.assertEqual(classify_cpp("{}"), "stub")


class TestClassifyCSharp(unittest.TestCase):
    def test_ok_return_is_stub(self):
        body = "{ return Ok(ctx); }"
        self.assertEqual(classify_csharp(body), "stub")

    def test_setreturn_zero_is_stub(self):
        body = "{ ctx.SetReturn(0); return; }"
        self.assertEqual(classify_csharp(body), "stub")

    def test_stubs_namespace(self):
        body = "{ var x = ctx.Memory.Read<int>(0); return x; }"
        self.assertEqual(classify_csharp(body, in_stubs_namespace=True), "stub")

    def test_real_body(self):
        body = "{ if (ctx.Memory.ReadByte(addr) != 0) { ctx.SetReturn(1); } return Ok(ctx); }"
        self.assertEqual(classify_csharp(body), "implemented")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestAnyPs5Scanner(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "core" / "libs" / "prx" / "libSceTest.native" / "src"
            _write(
                src / "a.cpp",
                """
int APS5_VABI sceTestStub(uint32_t context) {
    (void)context;
    return 0;
}

int APS5_VABI sceTestReal(uint32_t context) {
    if (context == 0) return -1;
    return context + 1;
}
""",
            )
            _write(
                src / "b.cpp",
                """
void init() {
    APS5_EXPORT("AAAAAAAAAAA", sceTestStub);
}
""",
            )
            records = scan_anyps5(root, github="o/r", sha="deadbeef", scan="core/libs/prx")
        by_name = {r["name"]: r for r in records}
        self.assertIn("sceTestStub", by_name)
        self.assertIn("sceTestReal", by_name)
        self.assertEqual(by_name["sceTestStub"]["status"], "stub")
        self.assertEqual(by_name["sceTestReal"]["status"], "implemented")
        self.assertEqual(by_name["sceTestReal"]["library"], "libSceTest")
        self.assertTrue(by_name["sceTestReal"]["url"].startswith("https://github.com/o/r/blob/deadbeef/"))
        self.assertTrue(by_name["sceTestReal"]["url"].endswith("#L" + str(by_name["sceTestReal"]["line"])))


class TestKytyScanner(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "src" / "libs" / "libs.h",
                """
LIB_NAME("libkernel", "libkernel");
LIB_FUNC("AAAAAAAAAAA", Posix::sem_trywait);
""",
            )
            _write(
                root / "src" / "kernel" / "sem.cpp",
                """
int sem_trywait(sem_t* sem) {
    if (sem == nullptr) return -1;
    return 0;
}
""",
            )
            records = scan_kyty(root, github="o/r", sha="abc123", scan="src/libs", resolve="src")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["nid"], "AAAAAAAAAAA")
        self.assertEqual(rec["name"], "sem_trywait")
        self.assertEqual(rec["status"], "implemented")
        self.assertEqual(rec["library"], "libkernel")

    def test_unresolved_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "src" / "libs" / "libs.h",
                'LIB_FUNC("BBBBBBBBBBB", Posix::missing_fn);\n',
            )
            records = scan_kyty(root, github="o/r", sha="abc123", scan="src/libs", resolve="src")
        self.assertEqual(records[0]["status"], "unknown")


class TestSharpEmuScanner(unittest.TestCase):
    def test_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "src" / "SharpEmu.Libs" / "Audio" / "A.cs",
                """
namespace SharpEmu.Libs.Audio
{
    public static class AjmExports
    {
        [SysAbiExport(
            Nid = "pIpGiaYkHkM",
            ExportName = "sceAjmMemoryUnregister",
            Target = Generation.Gen4 | Generation.Gen5,
            LibraryName = "libSceAjm")]
        public static long sceAjmMemoryUnregister(IGpuContext ctx, long ptr)
        {
            return Ok(ctx);
        }

        [SysAbiExport(ExportName = "sceTestReal", LibraryName = "libSceTest")]
        public static long sceTestReal(IGpuContext ctx, long addr)
        {
            if (ctx.Memory.ReadByte(addr) != 0)
            {
                ctx.SetReturn(1);
            }
            return Ok(ctx);
        }
    }
}
""",
            )
            records = scan_sharpemu(root, github="o/r", sha="feed", scan="src/SharpEmu.Libs")
        by_name = {r["name"]: r for r in records}
        self.assertEqual(by_name["sceAjmMemoryUnregister"]["nid"], "pIpGiaYkHkM")
        self.assertEqual(by_name["sceAjmMemoryUnregister"]["status"], "stub")
        self.assertEqual(by_name["sceAjmMemoryUnregister"]["library"], "libSceAjm")
        self.assertEqual(by_name["sceTestReal"]["status"], "implemented")
        self.assertEqual(by_name["sceTestReal"]["nid"], compute_nid("sceTestReal"))


class TestMerge(unittest.TestCase):
    def test_merge_two_emulators(self):
        scans = {
            "anyps5": [
                {
                    "nid": "pIpGiaYkHkM",
                    "name": "sceAjmMemoryUnregister",
                    "library": "libSceAjm",
                    "status": "stub",
                    "path": "core/libs/prx/x.cpp",
                    "line": 10,
                    "sha": "aaa",
                    "url": "https://example/a",
                    "emulator": "anyps5",
                }
            ],
            "kyty": [],
            "sharpemu": [
                {
                    "nid": "pIpGiaYkHkM",
                    "name": "sceAjmMemoryUnregister",
                    "library": "libSceAjm",
                    "status": "implemented",
                    "path": "src/SharpEmu.Libs/A.cs",
                    "line": 20,
                    "sha": "bbb",
                    "url": "https://example/b",
                    "emulator": "sharpemu",
                }
            ],
        }
        merged = merge_records(scans)
        self.assertEqual(len(merged), 1)
        item = merged[0]
        self.assertEqual(item["name"], "sceAjmMemoryUnregister")
        self.assertEqual(item["library"], "libSceAjm")
        self.assertEqual(item["emulators"]["anyps5"]["status"], "stub")
        self.assertEqual(item["emulators"]["kyty"]["status"], "not_implemented")
        self.assertEqual(item["emulators"]["sharpemu"]["status"], "implemented")
        self.assertIsNone(item["emulators"]["kyty"]["url"])

    def test_pick_name_prefers_hash_verified(self):
        entries = {
            "a": {"name": "sceAjmMemoryUnregister"},
            "b": {"name": "somethingElse"},
        }
        self.assertEqual(pick_name("pIpGiaYkHkM", entries), "sceAjmMemoryUnregister")


if __name__ == "__main__":
    unittest.main()
