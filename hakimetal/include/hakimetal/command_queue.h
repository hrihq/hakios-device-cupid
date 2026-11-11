#ifndef HAKIMETAL_COMMAND_QUEUE_H
#define HAKIMETAL_COMMAND_QUEUE_H

#include "hakimetal/backend.h"

#include <memory>

namespace hakimetal {

class CommandQueue {
public:
    CommandQueue() = default;
    CommandQueue(std::shared_ptr<IBackendCommandQueue> queue, Capabilities capabilities)
        : queue_(std::move(queue)), capabilities_(capabilities) {}

    bool valid() const { return queue_ != nullptr; }
    const Capabilities& capabilities() const { return capabilities_; }

    Result<CommandBuffer> create_command_buffer();

private:
    std::shared_ptr<IBackendCommandQueue> queue_;
    Capabilities capabilities_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_COMMAND_QUEUE_H
