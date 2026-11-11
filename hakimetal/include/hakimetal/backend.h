#ifndef HAKIMETAL_BACKEND_H
#define HAKIMETAL_BACKEND_H

// The backend interface.
//
// A backend says what it can do (capabilities) and does it (create_*). It never claims more than it
// has: an operation it cannot perform returns Status::Unsupported, and a backend that is not present
// returns Status::NotAvailable. The frontend turns neither into a fake success.
//
// The backend-side resource types are deliberately opaque to an application. The frontend classes
// (device.h, buffer.h, ...) wrap them.

#include "hakimetal/types.h"

#include <memory>
#include <vector>

namespace hakimetal {

// -------------------------------------------------------------------------------------------
// Backend-side resources
// -------------------------------------------------------------------------------------------

struct IBackendResource {
    virtual ~IBackendResource() = default;
};

class IBackendBuffer;
class IBackendTexture;
class IBackendCommandQueue;
class IBackendCommandBuffer;
class IBackendRenderPipeline;
class IBackendFence;
class IBackendEvent;
class IBackendDevice;

class IBackendBuffer : public IBackendResource {
public:
    virtual uint64_t length() const = 0;
    virtual StorageMode storage_mode() const = 0;
};

class IBackendTexture : public IBackendResource {
public:
    virtual const TextureDescriptor& descriptor() const = 0;
};

class IBackendCommandQueue : public IBackendResource {
public:
    virtual Result<std::shared_ptr<IBackendCommandBuffer>> create_command_buffer() = 0;
};

class IBackendCommandBuffer : public IBackendResource {
public:
    virtual Status commit() = 0;
    virtual Status wait_until_completed() = 0;
    virtual Status buffer_barrier(const std::shared_ptr<IBackendBuffer>& buffer,
                                  const BarrierDescriptor& descriptor) = 0;
    virtual Status texture_barrier(const std::shared_ptr<IBackendTexture>& texture,
                                   const BarrierDescriptor& descriptor) = 0;
    // The render pass descriptor is defined in command_buffer.h; the backend only sees a reference.
    virtual Result<std::shared_ptr<IBackendResource>> begin_render_pass(const void* descriptor) = 0;
};

// The encoder operations a frontend can issue inside a render pass. A backend that cannot do one
// returns Unsupported for that call; it does not skip it.
class IBackendRenderCommandEncoder : public IBackendResource {
public:
    virtual Status set_render_pipeline(const std::shared_ptr<IBackendRenderPipeline>& pipeline) = 0;
    virtual Status set_vertex_buffer(const std::shared_ptr<IBackendBuffer>& buffer, uint64_t offset,
                                     uint32_t index) = 0;
    virtual Status set_fragment_texture(const std::shared_ptr<IBackendTexture>& texture,
                                        uint32_t index) = 0;
    virtual Status set_blend_color(float red, float green, float blue, float alpha) = 0;
    virtual Status set_depth_stencil_state(CompareFunction compare, bool write_enabled) = 0;
    virtual Status draw(PrimitiveType type, uint32_t vertex_start, uint32_t vertex_count) = 0;
    virtual Status draw_indexed(PrimitiveType type, uint32_t index_count,
                                const std::shared_ptr<IBackendBuffer>& index_buffer,
                                uint64_t index_buffer_offset) = 0;
    virtual Status end_encoding() = 0;
};

class IBackendRenderPipeline : public IBackendResource {
public:
    virtual const RenderPipelineDescriptor& descriptor() const = 0;
};

class IBackendFence : public IBackendResource {
public:
    virtual Status wait(uint64_t timeout_ns) = 0;
    virtual Status signal(uint64_t value) = 0;
};

class IBackendEvent : public IBackendResource {
public:
    virtual Status notify(uint64_t value) = 0;
    virtual uint64_t value() const = 0;
};

class IBackendDevice : public IBackendResource {
public:
    virtual const Capabilities& capabilities() const = 0;
    virtual std::vector<const char*> supported_extensions() const = 0;
    virtual Result<std::shared_ptr<IBackendCommandQueue>>
        create_command_queue(const CommandQueueDescriptor& descriptor) = 0;
    virtual Result<std::shared_ptr<IBackendBuffer>>
        create_buffer(const BufferDescriptor& descriptor) = 0;
    virtual Result<std::shared_ptr<IBackendTexture>>
        create_texture(const TextureDescriptor& descriptor) = 0;
    virtual Result<std::shared_ptr<IBackendRenderPipeline>>
        create_render_pipeline(const RenderPipelineDescriptor& descriptor) = 0;
    virtual Result<std::shared_ptr<IBackendFence>>
        create_fence(const FenceDescriptor& descriptor) = 0;
    virtual Result<std::shared_ptr<IBackendEvent>>
        create_event(const EventDescriptor& descriptor) = 0;
};

// -------------------------------------------------------------------------------------------
// The backend
// -------------------------------------------------------------------------------------------

class IBackend {
public:
    virtual ~IBackend() = default;

    virtual const char* name() const = 0;
    virtual Capabilities capabilities() const = 0;
    virtual Result<std::shared_ptr<IBackendDevice>>
        create_device(const DeviceDescriptor& descriptor) = 0;

    // Vulkan extension names this backend can actually use, or an empty list for a non-Vulkan
    // backend. The frontend reports these verbatim; it does not invent them.
    virtual std::vector<const char*> supported_extensions() const = 0;
};

using BackendPtr = std::shared_ptr<IBackend>;

}   // namespace hakimetal

#endif   // HAKIMETAL_BACKEND_H
