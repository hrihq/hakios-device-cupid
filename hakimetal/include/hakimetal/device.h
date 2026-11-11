#ifndef HAKIMETAL_DEVICE_H
#define HAKIMETAL_DEVICE_H

// The device: the entry point to a backend, and the object every other object comes from.

#include "hakimetal/backend.h"
#include "hakimetal/buffer.h"
#include "hakimetal/command_queue.h"
#include "hakimetal/render_pipeline.h"
#include "hakimetal/synchronization.h"
#include "hakimetal/texture.h"

#include <memory>
#include <vector>

namespace hakimetal {

class Device {
public:
    Device() = default;
    explicit Device(std::shared_ptr<IBackendDevice> device) : device_(std::move(device)) {}

    bool valid() const { return device_ != nullptr; }
    const char* name() const { return device_ ? device_->capabilities().backend_name : "none"; }

    const Capabilities& capabilities() const {
        static const Capabilities none{};
        return device_ ? device_->capabilities() : none;
    }

    std::vector<const char*> supported_extensions() const {
        return device_ ? device_->supported_extensions() : std::vector<const char*>{};
    }

    Result<CommandQueue> create_command_queue(const CommandQueueDescriptor& descriptor = {});
    Result<Buffer> create_buffer(const BufferDescriptor& descriptor);
    Result<Texture> create_texture(const TextureDescriptor& descriptor);
    Result<RenderPipeline> create_render_pipeline(const RenderPipelineDescriptor& descriptor);
    Result<Fence> create_fence(const FenceDescriptor& descriptor = {});
    Result<Event> create_event(const EventDescriptor& descriptor = {});

private:
    std::shared_ptr<IBackendDevice> device_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_DEVICE_H
