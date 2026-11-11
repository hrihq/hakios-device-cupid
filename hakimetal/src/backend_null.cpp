#include "hakimetal/hakimetal.h"

namespace hakimetal {
namespace {

// A backend that is always present and supports nothing. It exists so that the frontend has something
// to talk to in tests and so that an application gets a clear "unsupported" rather than a crash.
class NullBackendDevice final : public IBackendDevice {
public:
    const Capabilities& capabilities() const override { return capabilities_; }
    std::vector<const char*> supported_extensions() const override { return {}; }
    Result<std::shared_ptr<IBackendCommandQueue>>
        create_command_queue(const CommandQueueDescriptor&) override {
        return Result<std::shared_ptr<IBackendCommandQueue>>(Status::Unsupported);
    }
    Result<std::shared_ptr<IBackendBuffer>> create_buffer(const BufferDescriptor&) override {
        return Result<std::shared_ptr<IBackendBuffer>>(Status::Unsupported);
    }
    Result<std::shared_ptr<IBackendTexture>> create_texture(const TextureDescriptor&) override {
        return Result<std::shared_ptr<IBackendTexture>>(Status::Unsupported);
    }
    Result<std::shared_ptr<IBackendRenderPipeline>>
        create_render_pipeline(const RenderPipelineDescriptor&) override {
        return Result<std::shared_ptr<IBackendRenderPipeline>>(Status::Unsupported);
    }
    Result<std::shared_ptr<IBackendFence>> create_fence(const FenceDescriptor&) override {
        return Result<std::shared_ptr<IBackendFence>>(Status::Unsupported);
    }
    Result<std::shared_ptr<IBackendEvent>> create_event(const EventDescriptor&) override {
        return Result<std::shared_ptr<IBackendEvent>>(Status::Unsupported);
    }

private:
    Capabilities capabilities_;
};

class NullBackend final : public IBackend {
public:
    const char* name() const override { return "null"; }
    Capabilities capabilities() const override { return Capabilities{}; }
    Result<std::shared_ptr<IBackendDevice>> create_device(const DeviceDescriptor&) override {
        return Result<std::shared_ptr<IBackendDevice>>(std::make_shared<NullBackendDevice>());
    }
    std::vector<const char*> supported_extensions() const override { return {}; }
};

}   // namespace

BackendPtr create_null_backend() {
    return std::make_shared<NullBackend>();
}

}   // namespace hakimetal
