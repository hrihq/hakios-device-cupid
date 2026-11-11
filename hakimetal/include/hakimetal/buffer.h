#ifndef HAKIMETAL_BUFFER_H
#define HAKIMETAL_BUFFER_H

// A buffer handle. The backend owns the memory; the frontend owns the placement rules.

#include "hakimetal/backend.h"

#include <memory>

namespace hakimetal {

class Buffer {
public:
    Buffer() = default;
    Buffer(std::shared_ptr<IBackendBuffer> buffer, Capabilities capabilities)
        : buffer_(std::move(buffer)), capabilities_(capabilities) {}

    bool valid() const { return buffer_ != nullptr; }
    uint64_t length() const { return buffer_ ? buffer_->length() : 0; }
    StorageMode storage_mode() const { return buffer_ ? buffer_->storage_mode() : StorageMode::Private; }
    const Capabilities& capabilities() const { return capabilities_; }

    // The backend handle, for a caller that wants to bind it in a pass.
    std::shared_ptr<IBackendBuffer> handle() const { return buffer_; }

private:
    std::shared_ptr<IBackendBuffer> buffer_;
    Capabilities capabilities_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_BUFFER_H
