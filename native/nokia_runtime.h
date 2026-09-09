#ifndef NOKIA_RUNTIME_H
#define NOKIA_RUNTIME_H

#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define NOKIA_RUNTIME_EXPORT __declspec(dllexport)
#else
#define NOKIA_RUNTIME_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct NokiaRuntime NokiaRuntime;

typedef void (*NokiaRuntimePcmCallback)(
    void *user, const int16_t *samples, uint32_t sample_count,
    uint32_t sample_rate);
typedef void (*NokiaRuntimeIndexCallback)(void *user, uint32_t index);

typedef struct {
    NokiaRuntimePcmCallback pcm;
    NokiaRuntimeIndexCallback index;
    void *user;
} NokiaRuntimeCallbacks;

NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5320(
    const uint8_t *rom, size_t rom_size,
    const char *resource_root_utf8,
    uint32_t language_id, uint32_t voice_id);

/* Preferred native-only constructor. The snapshot is produced at build time
   after CDevTTS, scheduler and style construction. No emulator is involved
   while this function restores it. */
NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5320_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *snapshot, size_t snapshot_size);

/* Nokia 5500 snapshots use the same host-memory layout but retain the phone's
   real ROM base. A 5500 frontend AOT is linked into a profile-specific DLL. */
NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_5500_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *snapshot, size_t snapshot_size);

/* The E65 snapshot contains its ROFS-resident speech device after build-time
   binding; the shipped native runtime therefore needs no E32 loader. */
NOKIA_RUNTIME_EXPORT NokiaRuntime *nokia_runtime_create_e65_snapshot(
    const uint8_t *rom, size_t rom_size,
    const uint8_t *snapshot, size_t snapshot_size);

NOKIA_RUNTIME_EXPORT void nokia_runtime_destroy(NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT int nokia_runtime_set_rate(
    NokiaRuntime *runtime, double factor);
NOKIA_RUNTIME_EXPORT int nokia_runtime_set_pitch(
    NokiaRuntime *runtime, double factor);
NOKIA_RUNTIME_EXPORT int nokia_runtime_speak_utf16(
    NokiaRuntime *runtime, const uint16_t *text, uint32_t text_length,
    const NokiaRuntimeCallbacks *callbacks);
NOKIA_RUNTIME_EXPORT void nokia_runtime_cancel(NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT int nokia_runtime_last_error(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_failure(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_reg(
    const NokiaRuntime *runtime, uint32_t index);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_count(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_klatt_gain(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_frontend_ticks(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_audio_ticks(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint64_t nokia_runtime_first_pcm_ticks(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_text_chunks(
    const NokiaRuntime *runtime);
/* Number of effectively-silent PCM samples removed only at artificial
   long-text chunk joins.  This is a diagnostic export for regression tests. */
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_seam_trimmed_samples(
    const NokiaRuntime *runtime);
NOKIA_RUNTIME_EXPORT void nokia_runtime_rom_trace_reset(void);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_rom_trace_page_size(void);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_rom_trace_page_used(uint32_t page);
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_rom_trace_touched_pages(void);

#ifdef __cplusplus
}
#endif
#endif
