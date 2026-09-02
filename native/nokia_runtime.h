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

#ifdef __cplusplus
}
#endif
#endif
