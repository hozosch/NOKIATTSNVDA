#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define NOKIA_EXPORT __declspec(dllexport)
#else
#define NOKIA_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
    uint32_t type;
    uint32_t id;
    uint8_t *data;
    uint32_t size;
} NokiaConfigBlob;

static NokiaConfigBlob *blobs;
static uint32_t blob_count;
static uint32_t blob_capacity;

static NokiaConfigBlob *find_blob(uint32_t type, uint32_t id) {
    uint32_t i;
    for (i = 0; i < blob_count; ++i)
        if (blobs[i].type == type && blobs[i].id == id)
            return &blobs[i];
    return NULL;
}

NOKIA_EXPORT void nokia_clear_config_blobs(void) {
    uint32_t i;
    for (i = 0; i < blob_count; ++i) {
        free(blobs[i].data);
        blobs[i].data = NULL;
        blobs[i].size = 0;
    }
    free(blobs);
    blobs = NULL;
    blob_count = 0;
    blob_capacity = 0;
}

NOKIA_EXPORT int nokia_register_config_blob(uint32_t type, uint32_t id,
                                             const void *data,
                                             uint32_t size) {
    NokiaConfigBlob *entry;
    uint8_t *copy = NULL;
    if (size && !data) return 0;
    if (size) {
        copy = (uint8_t *)malloc(size);
        if (!copy) return 0;
        memcpy(copy, data, size);
    }
    entry = find_blob(type, id);
    if (!entry) {
        if (blob_count == blob_capacity) {
            uint32_t next = blob_capacity ? blob_capacity * 2u : 64u;
            NokiaConfigBlob *grown = (NokiaConfigBlob *)realloc(
                blobs, (size_t)next * sizeof(*blobs));
            if (!grown) {
                free(copy);
                return 0;
            }
            blobs = grown;
            blob_capacity = next;
        }
        entry = &blobs[blob_count++];
        entry->type = type;
        entry->id = id;
        entry->data = NULL;
        entry->size = 0;
    }
    free(entry->data);
    entry->data = copy;
    entry->size = size;
    return 1;
}

/* Internal API used by the generated frontend dispatcher. The returned data
   remains owned by this registry until nokia_clear_config_blobs is called. */
int nokia_find_config_blob(uint32_t type, uint32_t id,
                           const uint8_t **data, uint32_t *size) {
    NokiaConfigBlob *entry = find_blob(type, id);
    if (!entry || !data || !size) return 0;
    *data = entry->data;
    *size = entry->size;
    return 1;
}
