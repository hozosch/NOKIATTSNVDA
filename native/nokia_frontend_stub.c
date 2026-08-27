#include <stdint.h>
#include <stddef.h>

/* Non-5320 profiles do not install the complete frontend hook.  Keep the
   shared bridge linkable without pulling the 5320-specific generated code
   into every model DLL. */
int nokia_frontend_aot(
    uint8_t *heap, uint8_t *vtable, uint8_t *traps, uint8_t *pool,
    uint8_t *stack, const uint8_t *rom, uint32_t rom_base, size_t rom_size,
    uint32_t registers[17], uint32_t return_address, const void *host) {
    (void)heap; (void)vtable; (void)traps; (void)pool; (void)stack;
    (void)rom; (void)rom_base; (void)rom_size; (void)registers;
    (void)return_address; (void)host;
    return 0;
}

uint32_t nokia_frontend_resume_count(void) {
    return 0;
}

uint32_t nokia_frontend_resume_address(uint32_t index) {
    (void)index;
    return 0;
}
