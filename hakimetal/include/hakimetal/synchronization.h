#ifndef HAKIMETAL_SYNCHRONIZATION_H
#define HAKIMETAL_SYNCHRONIZATION_H

// Fences and events.
//
// Metal's documented model has a fence (host-visible, host-waited) and a shared event that can notify
// a CPU listener when a value is reached. Vulkan's closest mechanisms are VkFence and timeline
// semaphores; neither has a CPU callback. A backend reports what it can do and the caller must not
// assume a callback exists.

#include "hakimetal/backend.h"

#include <functional>
#include <memory>

namespace hakimetal {

class Fence {
public:
    Fence() = default;
    Fence(std::shared_ptr<IBackendFence> fence) : fence_(std::move(fence)) {}

    bool valid() const { return fence_ != nullptr; }

    Status wait(uint64_t timeout_ns) { return fence_ ? fence_->wait(timeout_ns) : Status::NotAvailable; }
    Status signal(uint64_t value) { return fence_ ? fence_->signal(value) : Status::NotAvailable; }

private:
    std::shared_ptr<IBackendFence> fence_;
};

class Event {
public:
    using NotificationHandler = std::function<void(uint64_t value)>;

    Event() = default;
    Event(std::shared_ptr<IBackendEvent> event) : event_(std::move(event)) {}

    bool valid() const { return event_ != nullptr; }

    Status notify(uint64_t value) { return event_ ? event_->notify(value) : Status::NotAvailable; }
    uint64_t value() const { return event_ ? event_->value() : 0; }

    // Metal's shared-event notification is a CPU-side callback. A Vulkan backend has no equivalent;
    // register_handler returns Unsupported unless the backend can deliver it. The frontend never
    // pretends a handler will be called.
    Status register_handler(const NotificationHandler& handler) {
        handler_ = handler;
        // The backend-side event carries the handle; the frontend keeps the handler for the caller's
        // own polling if the backend cannot call it.
        return Status::Unsupported;
    }

    const NotificationHandler& handler() const { return handler_; }

private:
    std::shared_ptr<IBackendEvent> event_;
    NotificationHandler handler_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_SYNCHRONIZATION_H
