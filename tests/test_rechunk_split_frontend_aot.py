from __future__ import annotations

import unittest

from tools.rechunk_split_frontend_aot import rechunk_source


PREFIX = """typedef struct { unsigned reg_pc; } NokiaFrontendState;
typedef struct { int unused; } NokiaFrontendMachine;
typedef struct { int unused; } NokiaFrontendHost;
#define reg_pc (state->reg_pc)
enum { NOKIA_FRONTEND_YIELDED=2, NOKIA_FRONTEND_CONTINUE=3 };

"""

SUFFIX = """

typedef int (*NokiaFrontendChunk)(NokiaFrontendState*,NokiaFrontendMachine*,const NokiaFrontendHost*);
static NokiaFrontendChunk nokia_frontend_chunks[]={
    nokia_frontend_chunk_0,
};
static const uint32_t nokia_frontend_chunk_limits[]={
    0x0000100cu,
};

static int tail(void){return 1;}
"""


class RechunkSplitFrontendAotTest(unittest.TestCase):
    def test_splits_and_routes_new_cross_chunk_jump(self) -> None:
        blocks = []
        for address in range(0x1000, 0x1010, 4):
            following = address + 4
            blocks.extend((
                f"L_{address:08x}:",
                f"    reg_pc={address};",
                (
                    f"    goto L_{following:08x};"
                    if following < 0x1010
                    else "    return NOKIA_FRONTEND_YIELDED;"
                ),
            ))
        source = PREFIX + "\n".join((
            "static int nokia_frontend_chunk_0(NokiaFrontendState*state,",
            " NokiaFrontendMachine*machine_ptr,const NokiaFrontendHost*host){",
            "    switch((uint32_t)reg_pc&~1u){",
            *(f"    case 0x{address:08x}u: goto L_{address:08x};"
              for address in range(0x1000, 0x1010, 4)),
            "    default: return NOKIA_FRONTEND_YIELDED;",
            "    }",
            *blocks,
            "}",
        )) + SUFFIX

        output = rechunk_source(source, max_lines=16)

        self.assertEqual(output.count("static int nokia_frontend_chunk_"), 2)
        self.assertIn(
            "reg_pc=UINT64_C(4104); return NOKIA_FRONTEND_CONTINUE;",
            output,
        )
        for address in range(0x1000, 0x1010, 4):
            self.assertEqual(output.count(f"L_{address:08x}:"), 1)
        self.assertIn("static int tail(void){return 1;}", output)
        self.assertEqual(rechunk_source(output, max_lines=16), output)

    def test_restores_old_dispatcher_hops_when_target_is_now_local(self) -> None:
        source = PREFIX + "\n".join((
            "static int nokia_frontend_chunk_0(NokiaFrontendState*state,",
            " NokiaFrontendMachine*machine_ptr,const NokiaFrontendHost*host){",
            "    switch((uint32_t)reg_pc&~1u){",
            "    case 0x00001000u: goto L_00001000;",
            "    case 0x00001004u: goto L_00001004;",
            "    case 0x00001008u: goto L_00001008;",
            "    default: return NOKIA_FRONTEND_YIELDED;",
            "    }",
            "L_00001000:",
            "    reg_pc=UINT64_C(4100); return NOKIA_FRONTEND_CONTINUE;",
            "L_00001004:",
            "    if (reg_pc) { reg_pc=UINT64_C(4104); return NOKIA_FRONTEND_CONTINUE; }",
            "    goto L_00001008;",
            "L_00001008:",
            "    return NOKIA_FRONTEND_YIELDED;",
            "}",
        )) + SUFFIX.replace("0x0000100cu", "0x00001008u")

        output = rechunk_source(source, max_lines=64)

        self.assertIn("goto L_00001004;", output)
        self.assertIn("if (reg_pc) goto L_00001008;", output)
        self.assertNotIn(
            "reg_pc=UINT64_C(4100); return NOKIA_FRONTEND_CONTINUE;",
            output,
        )
        self.assertNotIn(
            "reg_pc=UINT64_C(4104); return NOKIA_FRONTEND_CONTINUE;",
            output,
        )
        self.assertEqual(rechunk_source(output, max_lines=64), output)

    def test_rejects_too_small_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 16"):
            rechunk_source("source", max_lines=15)


if __name__ == "__main__":
    unittest.main()
