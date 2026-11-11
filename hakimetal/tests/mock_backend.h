#ifndef HAKIMETAL_TESTS_MOCK_BACKEND_H
#define HAKIMETAL_TESTS_MOCK_BACKEND_H

// A backend that records every call and returns configured results. It touches no hardware, which is
// the whole point: the frontend's logic is testable without a GPU and without Vulkan.

#include "hakimetal/hakimetal.h"

#include <memory>
#include <string>
#include <vector>

namespace hakimetal {
namespace testing {

class MockBuffer final : public IBackendBuffer {
public:
    MockBuffer(uint64_t length, StorageMode storage) : length_(length), storage_(storage) {}
    uint64_t length() const override { return length_; }
    StorageMode storage_mode() const override { return storage_; }

private:
    uint64_t length_;
    StorageMode storage_;
};

class MockTexture final : public IBackendTexture {
public:
    explicit MockTexture(TextureDescriptor descriptor) : descriptor_(descriptor) {}
    const TextureDescriptor& descriptor() const override { return descriptor_; }

private:
    TextureDescriptor descriptor_;
};

class MockRenderPipeline final : public IBackendRenderPipeline {
public:
    explicit MockRenderPipeline(RenderPipelineDescriptor descriptor) : descriptor_(descriptor) {}
    const RenderPipelineDescriptor& descriptor() const override { return descriptor_; }

private:
    RenderPipelineDescriptor descriptor_;
};

class MockFence final : public IBackendFence {
public:
    Status wait(uint64_t timeout_ns) override {
        calls.push_back("fence.wait");
        last_timeout = timeout_ns;
        return Status::Ok;
    }
    Status signal(uint64_t value) override {
        calls.push_back("fence.signal");
        last_value = value;
        return Status::Ok;
    }

    std::vector<std::string> calls;
    uint64_t last_timeout = 0;
    uint64_t last_value = 0;
};

class MockEvent final : public IBackendEvent {
public:
    Status notify(uint64_t value) override {
        calls.push_back("event.notify");
        last_value = value;
        return Status::Ok;
    }
    uint64_t value() const override { return last_value; }

    std::vector<std::string> calls;
    uint64_t last_value = 0;
};

class MockRenderCommandEncoder final : public IBackendRenderCommandEncoder {
public:
    Status set_render_pipeline(const std::shared_ptr<IBackendRenderPipeline>&) override {
        calls.push_back("encoder.set_render_pipeline");
        return Status::Ok;
    }
    Status set_vertex_buffer(const std::shared_ptr<IBackendBuffer>&, uint64_t, uint32_t index) override {
        calls.push_back("encoder.set_vertex_buffer");
        last_vertex_buffer_index = index;
        return Status::Ok;
    }
    Status set_fragment_texture(const std::shared_ptr<IBackendTexture>&, uint32_t index) override {
        calls.push_back("encoder.set_fragment_texture");
        last_fragment_texture_index = index;
        return Status::Ok;
    }
    Status set_blend_color(float red, float green, float blue, float alpha) override {
        calls.push_back("encoder.set_blend_color");
        blend_color[0] = red; blend_color[1] = green; blend_color[2] = blue; blend_color[3] = alpha;
        return Status::Ok;
    }
    Status set_depth_stencil_state(CompareFunction compare, bool write_enabled) override {
        calls.push_back("encoder.set_depth_stencil_state");
        last_compare = compare;
        last_depth_write = write_enabled;
        return Status::Ok;
    }
    Status draw(PrimitiveType type, uint32_t start, uint32_t count) override {
        calls.push_back("encoder.draw");
        last_primitive = type;
        last_draw_start = start;
        last_draw_count = count;
        return Status::Ok;
    }
    Status draw_indexed(PrimitiveType type, uint32_t count,
                        const std::shared_ptr<IBackendBuffer>&, uint64_t offset) override {
        calls.push_back("encoder.draw_indexed");
        last_indexed_count = count;
        last_index_offset = offset;
        return Status::Ok;
    }
    Status end_encoding() override {
        calls.push_back("encoder.end_encoding");
        return Status::Ok;
    }

    std::vector<std::string> calls;
    uint32_t last_vertex_buffer_index = 0;
    uint32_t last_fragment_texture_index = 0;
    float blend_color[4] = {};
    CompareFunction last_compare = CompareFunction::Always;
    bool last_depth_write = false;
    PrimitiveType last_primitive = PrimitiveType::Triangle;
    uint32_t last_draw_start = 0;
    uint32_t last_draw_count = 0;
    uint32_t last_indexed_count = 0;
    uint64_t last_index_offset = 0;
};

class MockCommandBuffer final : public IBackendCommandBuffer {
public:
    explicit MockCommandBuffer(std::shared_ptr<MockRenderCommandEncoder> encoder)
        : encoder_(std::move(encoder)) {}

    Status commit() override {
        calls.push_back("command_buffer.commit");
        return Status::Ok;
    }
    Status wait_until_completed() override {
        calls.push_back("command_buffer.wait_until_completed");
        return Status::Ok;
    }
    Status buffer_barrier(const std::shared_ptr<IBackendBuffer>&, const BarrierDescriptor& d) override {
        calls.push_back("command_buffer.buffer_barrier");
        last_buffer_barrier = d;
        return Status::Ok;
    }
    Status texture_barrier(const std::shared_ptr<IBackendTexture>&, const BarrierDescriptor& d) override {
        calls.push_back("command_buffer.texture_barrier");
        last_texture_barrier = d;
        return Status::Ok;
    }
    Result<std::shared_ptr<IBackendResource>> begin_render_pass(const void*) override {
        calls.push_back("command_buffer.begin_render_pass");
        return Result<std::shared_ptr<IBackendResource>>(encoder_);
    }

    std::vector<std::string> calls;
    BarrierDescriptor last_buffer_barrier;
    BarrierDescriptor last_texture_barrier;

private:
    std::shared_ptr<MockRenderCommandEncoder> encoder_;
};

class MockCommandQueue final : public IBackendCommandQueue {
public:
    explicit MockCommandQueue(std::shared_ptr<MockCommandBuffer> buffer)
        : buffer_(std::move(buffer)) {}

    Result<std::shared_ptr<IBackendCommandBuffer>> create_command_buffer() override {
        calls.push_back("queue.create_command_buffer");
        return Result<std::shared_ptr<IBackendCommandBuffer>>(buffer_);
    }

    std::vector<std::string> calls;

private:
    std::shared_ptr<MockCommandBuffer> buffer_;
};

class MockDevice final : public IBackendDevice {
public:
    explicit MockDevice(Capabilities capabilities) : capabilities_(capabilities) {}

    const Capabilities& capabilities() const override { return capabilities_; }

    Result<std::shared_ptr<IBackendCommandQueue>>
        create_command_queue(const CommandQueueDescriptor&) override {
        calls.push_back("device.create_command_queue");
        return Result<std::shared_ptr<IBackendCommandQueue>>(queue_);
    }
    Result<std::shared_ptr<IBackendBuffer>> create_buffer(const BufferDescriptor& descriptor) override {
        calls.push_back("device.create_buffer");
        auto buffer = std::make_shared<MockBuffer>(descriptor.length, descriptor.storage_mode);
        buffers.push_back(buffer);
        return Result<std::shared_ptr<IBackendBuffer>>(buffer);
    }
    Result<std::shared_ptr<IBackendTexture>> create_texture(const TextureDescriptor& descriptor) override {
        calls.push_back("device.create_texture");
        auto texture = std::make_shared<MockTexture>(descriptor);
        textures.push_back(texture);
        return Result<std::shared_ptr<IBackendTexture>>(texture);
    }
    Result<std::shared_ptr<IBackendRenderPipeline>>
        create_render_pipeline(const RenderPipelineDescriptor& descriptor) override {
        calls.push_back("device.create_render_pipeline");
        if (!capabilities_.shader_translation) {
            return Result<std::shared_ptr<IBackendRenderPipeline>>(Status::Unsupported);
        }
        auto pipeline = std::make_shared<MockRenderPipeline>(descriptor);
        pipelines.push_back(pipeline);
        return Result<std::shared_ptr<IBackendRenderPipeline>>(pipeline);
    }
    Result<std::shared_ptr<IBackendFence>> create_fence(const FenceDescriptor&) override {
        calls.push_back("device.create_fence");
        auto fence = std::make_shared<MockFence>();
        fences.push_back(fence);
        return Result<std::shared_ptr<IBackendFence>>(fence);
    }
    Result<std::shared_ptr<IBackendEvent>> create_event(const EventDescriptor&) override {
        calls.push_back("device.create_event");
        auto event = std::make_shared<MockEvent>();
        events.push_back(event);
        return Result<std::shared_ptr<IBackendEvent>>(event);
    }

    std::vector<std::string> calls;
    std::shared_ptr<MockCommandQueue> queue_;
    std::vector<std::shared_ptr<MockBuffer>> buffers;
    std::vector<std::shared_ptr<MockTexture>> textures;
    std::vector<std::shared_ptr<MockRenderPipeline>> pipelines;
    std::vector<std::shared_ptr<MockFence>> fences;
    std::vector<std::shared_ptr<MockEvent>> events;

private:
    Capabilities capabilities_;
};

class MockBackend final : public IBackend {
public:
    explicit MockBackend(Capabilities capabilities) : capabilities_(capabilities) {}

    const char* name() const override { return "mock"; }
    Capabilities capabilities() const override { return capabilities_; }

    Result<std::shared_ptr<IBackendDevice>> create_device(const DeviceDescriptor&) override {
        auto device = std::make_shared<MockDevice>(capabilities_);
        device_ = device;
        return Result<std::shared_ptr<IBackendDevice>>(device);
    }

    std::vector<const char*> supported_extensions() const override {
        return {"HKIMOCK_A", "HKIMOCK_B"};
    }

    std::shared_ptr<MockDevice> device() const { return device_; }

private:
    Capabilities capabilities_;
    std::shared_ptr<MockDevice> device_;
};

}   // namespace testing
}   // namespace hakimetal

#endif   // HAKIMETAL_TESTS_MOCK_BACKEND_H
