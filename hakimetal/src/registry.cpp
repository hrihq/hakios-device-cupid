#include "hakimetal/hakimetal.h"

namespace hakimetal {

Registry& Registry::instance() {
    static Registry registry;
    return registry;
}

void Registry::register_backend(BackendPtr backend) {
    if (backend) backends_.push_back(std::move(backend));
}

std::vector<const char*> Registry::backend_names() const {
    std::vector<const char*> names;
    names.reserve(backends_.size());
    for (const auto& backend : backends_) names.push_back(backend->name());
    return names;
}

BackendPtr Registry::find(const char* name) const {
    if (!name) return nullptr;
    for (const auto& backend : backends_) {
        if (std::string(backend->name()) == name) return backend;
    }
    return nullptr;
}

Capabilities Registry::capabilities(const char* name) const {
    BackendPtr backend = find(name);
    return backend ? backend->capabilities() : Capabilities{};
}

Result<std::shared_ptr<IBackendDevice>> Registry::create_device(const char* name,
                                                               const DeviceDescriptor& descriptor) {
    BackendPtr backend = find(name);
    if (!backend) return Result<std::shared_ptr<IBackendDevice>>(Status::NotAvailable);
    return backend->create_device(descriptor);
}

BackendPtr Registry::default_backend() const {
    return backends_.empty() ? nullptr : backends_.front();
}

Result<std::shared_ptr<IBackendDevice>> create_default_device(const DeviceDescriptor& descriptor) {
    BackendPtr backend = Registry::instance().default_backend();
    if (!backend) return Result<std::shared_ptr<IBackendDevice>>(Status::NotAvailable);
    return backend->create_device(descriptor);
}

}   // namespace hakimetal
