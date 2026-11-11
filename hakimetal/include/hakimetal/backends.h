#ifndef HAKIMETAL_BACKENDS_H
#define HAKIMETAL_BACKENDS_H

// The backends HakiMetal ships with. Each is a factory function returning an IBackend; the registry
// owns the instance. A backend that is present but cannot do something says so through its
// capabilities and through Status::Unsupported -- never by pretending.

#include "hakimetal/backend.h"

namespace hakimetal {

// Always present, supports nothing. Useful as a placeholder and in tests.
BackendPtr create_null_backend();

// Detects Vulkan at runtime. When Vulkan is absent its capabilities report available = false and
// every operation returns NotAvailable. Phase 1 does not create a device.
BackendPtr create_vulkan_backend();

}   // namespace hakimetal

#endif   // HAKIMETAL_BACKENDS_H
