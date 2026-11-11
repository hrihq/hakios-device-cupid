#ifndef HAKIMETAL_REGISTRY_H
#define HAKIMETAL_REGISTRY_H

// Backend discovery and selection.
//
// A backend is registered by the application or by the platform layer; the registry never creates a
// backend the application did not ask for. Selection is by name, and the caller can always ask what
// each backend can do before creating a device. Nothing here loads a driver or touches hardware.

#include "hakimetal/backend.h"

#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace hakimetal {

// The registry is a process-wide singleton, so it is safe to use from more than one thread: every
// public method takes the lock. The objects it hands out are not thread-safe; see backend.h.
class Registry {
public:
    static Registry& instance();

    // Take ownership of a backend. The registry keeps it alive for the process.
    void register_backend(BackendPtr backend);

    std::vector<const char*> backend_names() const;
    Capabilities capabilities(const char* name) const;
    BackendPtr find(const char* name) const;

    // Create a device from a named backend. Returns NotAvailable when the backend is absent.
    Result<std::shared_ptr<IBackendDevice>> create_device(const char* name,
                                                          const DeviceDescriptor& descriptor);

    // The backend HakiMetal would choose with no preference: the first registered one. An
    // application should not rely on this; it should ask for a name.
    BackendPtr default_backend() const;

private:
    Registry() = default;
    mutable std::mutex mutex_;
    std::vector<BackendPtr> backends_;
};

// Convenience: create a device from the first registered backend.
Result<std::shared_ptr<IBackendDevice>> create_default_device(const DeviceDescriptor& descriptor = {});

}   // namespace hakimetal

#endif   // HAKIMETAL_REGISTRY_H
