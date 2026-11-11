// HakiMetal unit tests. They run on a plain Linux runner with no GPU and no Vulkan: the MockBackend
// records calls and the frontend's logic is what is being verified.

#include "hakimetal/hakimetal.h"
#include "mock_backend.h"

#include <algorithm>
#include <cstdio>
#include <functional>
#include <string>
#include <thread>
#include <vector>

using namespace hakimetal;

namespace {

// A backend that answers Ok with a null handle. The frontend must turn that into BackendError rather
// than handing the caller an object with nothing behind it.
class NullQueueDevice final : public IBackendDevice {
public:
    const Capabilities& capabilities() const override { return capabilities_; }
    std::vector<const char*> supported_extensions() const override { return {}; }
    Result<std::shared_ptr<IBackendCommandQueue>>
        create_command_queue(const CommandQueueDescriptor&) override {
        return Result<std::shared_ptr<IBackendCommandQueue>>(
            std::shared_ptr<IBackendCommandQueue>{});
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

int g_failures = 0;
std::vector<std::string> g_tests;

void check(bool condition, const std::string& what) {
    if (!condition) {
        ++g_failures;
        std::fprintf(stderr, "    FAIL %s\n", what.c_str());
        std::fflush(stderr);
    }
}

void test(const std::string& name, std::function<void()> body) {
    g_tests.push_back(name);
    std::fprintf(stderr, "-> %s\n", name.c_str());
    std::fflush(stderr);
    const int before = g_failures;
    body();
    if (g_failures == before) {
        std::fprintf(stderr, "ok   %s\n", name.c_str());
    } else {
        std::fprintf(stderr, "FAIL %s\n", name.c_str());
    }
    std::fflush(stderr);
}

Capabilities mock_capabilities() {
    Capabilities caps;
    caps.backend_name = "mock";
    caps.available = true;
    caps.untracked_resources = false;   // the frontend must issue every barrier
    caps.managed_storage = false;
    caps.shader_translation = true;
    caps.max_texture_dimension = 8192;
    return caps;
}

std::shared_ptr<testing::MockBackend> make_mock() {
    auto backend = std::make_shared<testing::MockBackend>(mock_capabilities());
    auto device = backend->create_device(DeviceDescriptor{});
    if (!device) return nullptr;
    auto mock = backend->device();
    // give the mock device a queue whose command buffer carries a recording encoder
    auto encoder = std::make_shared<testing::MockRenderCommandEncoder>();
    auto buffer = std::make_shared<testing::MockCommandBuffer>(encoder);
    auto queue = std::make_shared<testing::MockCommandQueue>(buffer);
    mock->queue_ = queue;
    return backend;
}

}   // namespace

int main() {
    test("device creation reports the backend's capabilities", [] {
        auto backend = make_mock();
        auto device = backend->create_device(DeviceDescriptor{});
        check(static_cast<bool>(device), "device creation should succeed");
        check(device.value()->capabilities().backend_name == std::string("mock"),
              "capabilities should carry the backend name");
        check(device.value()->capabilities().available, "mock backend reports available");
    });

    test("the null backend reports nothing available", [] {
        auto null_backend = hakimetal::create_null_backend();
        Capabilities caps = null_backend->capabilities();
        check(!caps.available, "null backend must not report available");
        check(!caps.vulkan, "null backend must not report vulkan");
        check(null_backend->supported_extensions().empty(),
              "null backend must not invent extensions");
    });

    test("an absent backend is NotAvailable, never a fake success", [] {
        Device device;   // no backend
        check(!device.valid(), "an empty device is not valid");
        auto buffer = device.create_buffer(BufferDescriptor{});
        check(!buffer, "creating a buffer without a device fails");
        check(buffer.status() == Status::NotAvailable, "the status is NotAvailable, not Unsupported");
    });

    test("buffer creation round-trips the descriptor", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        BufferDescriptor descriptor;
        descriptor.length = 4096;
        descriptor.storage_mode = StorageMode::Private;
        auto buffer = device.create_buffer(descriptor);
        check(static_cast<bool>(buffer), "buffer creation should succeed");
        check(buffer.value().length() == 4096, "the length round-trips");
        check(buffer.value().storage_mode() == StorageMode::Private, "the storage mode round-trips");
        check(buffer.value().capabilities().untracked_resources == false,
              "the frontend carries the backend's capabilities");
    });

    test("texture creation round-trips the descriptor", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        TextureDescriptor descriptor;
        descriptor.width = 256;
        descriptor.height = 128;
        descriptor.format = TextureFormat::RGBA16Float;
        descriptor.mipmap_level_count = 3;
        auto texture = device.create_texture(descriptor);
        check(static_cast<bool>(texture), "texture creation should succeed");
        check(texture.value().descriptor().width == 256, "width round-trips");
        check(texture.value().descriptor().height == 128, "height round-trips");
        check(texture.value().descriptor().format == TextureFormat::RGBA16Float,
              "format round-trips");
        check(texture.value().descriptor().mipmap_level_count == 3, "mipmap count round-trips");
    });

    test("render pipeline creation is reported unsupported when there is no shader path", [] {
        Capabilities no_shader = mock_capabilities();
        no_shader.shader_translation = false;
        auto limited = std::make_shared<testing::MockBackend>(no_shader);
        Device limited_device(limited->create_device(DeviceDescriptor{}).value());
        auto pipeline = limited_device.create_render_pipeline(RenderPipelineDescriptor{});
        check(!pipeline, "without a shader path the pipeline must fail");
        check(pipeline.status() == Status::Unsupported,
              "the status is Unsupported, not BackendError or Ok");
    });

    test("a render pass records encoder calls and commits", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        auto queue = device.create_command_queue(CommandQueueDescriptor{});
        check(static_cast<bool>(queue), "queue creation should succeed");
        auto buffer = queue.value().create_command_buffer();
        check(static_cast<bool>(buffer), "command buffer creation should succeed");

        auto pipeline_result = device.create_render_pipeline(RenderPipelineDescriptor{});
        auto vertex_result = device.create_buffer(BufferDescriptor{64, StorageMode::Shared});
        auto texture_result = device.create_texture(TextureDescriptor{});

        RenderPassDescriptor pass{};
        pass.color_attachment_count = 1;
        pass.color_attachments[0].texture = texture_result.value().handle();
        pass.color_attachments[0].load_action = LoadAction::Clear;
        auto encoder = buffer.value().begin_render_pass(pass);
        check(static_cast<bool>(encoder), "begin_render_pass should succeed");
        check(encoder.value().set_render_pipeline(pipeline_result.value()) == Status::Ok,
              "set_render_pipeline succeeds");
        check(encoder.value().set_vertex_buffer(vertex_result.value(), 8, 0) == Status::Ok,
              "set_vertex_buffer succeeds");
        check(encoder.value().draw(PrimitiveType::Triangle, 0, 36) == Status::Ok, "draw succeeds");
        check(encoder.value().end_encoding() == Status::Ok, "end_encoding succeeds");
        check(buffer.value().commit() == Status::Ok, "commit succeeds");

        auto mock_device = backend->device();
        auto& calls = mock_device->queue_->buffer_->calls;
        check(std::find(calls.begin(), calls.end(), "command_buffer.begin_render_pass") != calls.end(),
              "the backend saw begin_render_pass");
        check(std::find(calls.begin(), calls.end(), "command_buffer.commit") != calls.end(),
              "the backend saw commit");
        auto& encoder_calls = mock_device->queue_->buffer_->encoder_->calls;
        check(std::find(encoder_calls.begin(), encoder_calls.end(), "encoder.draw") != encoder_calls.end(),
              "the backend saw draw");
    });

    test("the encoder rejects invalid arguments", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        auto queue = device.create_command_queue(CommandQueueDescriptor{}).value();
        auto buffer = queue.create_command_buffer().value();
        auto encoder = buffer.begin_render_pass(RenderPassDescriptor{}).value();

        Buffer invalid_buffer;   // not created from a device
        check(encoder.set_vertex_buffer(invalid_buffer, 0, 0) == Status::InvalidArgument,
              "an invalid buffer is rejected");
        Texture invalid_texture;
        check(encoder.set_fragment_texture(invalid_texture, 0) == Status::InvalidArgument,
              "an invalid texture is rejected");
        RenderPipeline invalid_pipeline;
        check(encoder.set_render_pipeline(invalid_pipeline) == Status::InvalidArgument,
              "an invalid pipeline is rejected");
    });

    test("the frontend forwards the barriers it owns", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        auto queue = device.create_command_queue(CommandQueueDescriptor{}).value();
        auto buffer_handle = queue.create_command_buffer().value();

        auto vertex = device.create_buffer(BufferDescriptor{128, StorageMode::Shared}).value();
        auto texture = device.create_texture(TextureDescriptor{}).value();

        BarrierDescriptor barrier{};
        barrier.source_stage = 1;
        barrier.destination_stage = 2;
        barrier.source_access = 4;
        barrier.destination_access = 8;

        check(buffer_handle.buffer_barrier(vertex, barrier) == Status::Ok,
              "the buffer barrier is forwarded");
        check(buffer_handle.texture_barrier(texture, barrier) == Status::Ok,
              "the texture barrier is forwarded");

        auto& mock_buffer = backend->device()->queue_->buffer_;
        check(mock_buffer->last_buffer_barrier.destination_stage == 2,
              "the barrier descriptor round-trips");
        check(mock_buffer->last_texture_barrier.source_access == 4,
              "the texture barrier descriptor round-trips");
    });

    test("fences and events forward to the backend", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        auto fence = device.create_fence(FenceDescriptor{}).value();
        check(fence.wait(1000) == Status::Ok, "fence.wait succeeds");
        check(fence.signal(7) == Status::Ok, "fence.signal succeeds");
        auto event = device.create_event(EventDescriptor{}).value();
        check(event.notify(3) == Status::Ok, "event.notify succeeds");
        check(event.value() == 3, "the event value round-trips");

        auto& fences = backend->device()->fences;
        check(!fences.empty() && fences[0]->last_value == 7, "the fence value reached the backend");
    });

    test("an event handler cannot be registered unless the backend can call it", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        auto event = device.create_event(EventDescriptor{}).value();
        int calls = 0;
        Status status = event.register_handler([&calls](uint64_t) { ++calls; });
        check(status == Status::Unsupported,
              "a Vulkan-shaped backend cannot deliver a CPU callback; it says so");
        check(calls == 0, "the handler was never called");
    });

    test("the registry selects a backend by name and reports absence", [] {
        auto& registry = Registry::instance();
        registry.register_backend(make_mock());
        registry.register_backend(hakimetal::create_null_backend());

        auto names = registry.backend_names();
        check(names.size() == 2, "two backends are registered");
        check(registry.find("mock") != nullptr, "the mock backend is found by name");
        check(registry.find("no-such-backend") == nullptr, "an absent backend is not found");

        auto caps = registry.capabilities("mock");
        check(caps.backend_name == std::string("mock"), "the registry reports the mock capabilities");
        check(registry.capabilities("absent").backend_name == std::string("null"),
              "an absent backend reports the null capabilities");

        auto device = registry.create_device("absent", DeviceDescriptor{});
        check(!device, "creating a device from an absent backend fails");
        check(device.status() == Status::NotAvailable, "the status is NotAvailable");
    });

    test("the Vulkan backend reports its real state and never claims a device it cannot make", [] {
        auto vulkan = hakimetal::create_vulkan_backend();
        Capabilities caps = vulkan->capabilities();
        if (!caps.vulkan) {
            check(!caps.available, "without Vulkan the backend is not available");
            check(caps.vulkan_api_version == 0, "without Vulkan there is no api version");
        } else {
            check(caps.vulkan_api_version != 0, "with Vulkan the api version is reported");
            check(!caps.shader_translation,
                  "Phase 1 does not claim a shader translation path");
        }
        auto device = vulkan->create_device(DeviceDescriptor{});
        check(!device, "Phase 1 does not create a Vulkan device");
        check(device.status() == Status::Unsupported,
              "the status is Unsupported, not BackendError");
        (void)0;
    });

    test("a default-constructed Result is not a success", [] {
        Result<Buffer> result;
        check(!result.ok(), "a default Result must not report ok");
        check(!static_cast<bool>(result), "a default Result must not convert to true");
        check(result.status() == Status::NotAvailable, "the status is NotAvailable");
        check(!result.has_value(), "there is no value");
    });

    test("a backend that answers Ok with a null handle is a BackendError, not an empty object", [] {
        Device device(std::make_shared<NullQueueDevice>());
        auto queue = device.create_command_queue(CommandQueueDescriptor{});
        check(!queue, "a null handle must not become a success");
        check(queue.status() == Status::BackendError, "the status is BackendError");
    });

    test("the render pass descriptor reaches the backend typed", [] {
        auto backend = make_mock();
        Device device(backend->create_device(DeviceDescriptor{}).value());
        auto queue = device.create_command_queue(CommandQueueDescriptor{}).value();
        auto command_buffer = queue.create_command_buffer().value();
        auto texture = device.create_texture(TextureDescriptor{}).value();

        RenderPassDescriptor pass{};
        pass.color_attachment_count = 2;
        pass.color_attachments[0].texture = texture.handle();
        pass.color_attachments[0].load_action = LoadAction::Clear;
        pass.color_attachments[0].clear_color[0] = 0.25f;
        auto encoder = command_buffer.begin_render_pass(pass);
        check(static_cast<bool>(encoder), "begin_render_pass should succeed");

        auto& mock_buffer = backend->device()->queue_->buffer_;
        check(mock_buffer->render_pass_color_attachment_count == 2,
              "the backend saw the descriptor's attachment count, not a void*");
        check(mock_buffer->render_pass_clear_color[0] == 0.25f,
              "the backend saw the descriptor's clear colour");
    });

    test("the registry takes its lock: concurrent registration and lookup do not crash", [] {
        auto& registry = Registry::instance();
        std::vector<std::thread> threads;
        for (int i = 0; i < 8; ++i) {
            threads.emplace_back([&registry, i] {
                for (int j = 0; j < 200; ++j) {
                    auto backend = std::make_shared<testing::MockBackend>(mock_capabilities());
                    backend->name();   // touch the object the registry will hold
                    registry.register_backend(backend);
                    (void)registry.find("mock");
                    (void)registry.backend_names();
                    (void)registry.capabilities("mock");
                    (void)registry.default_backend();
                    (void)registry.create_device("mock", DeviceDescriptor{});
                }
                (void)i;
            });
        }
        for (auto& thread : threads) thread.join();
        check(true, "the registry survived concurrent use");
    });

    std::fprintf(stderr, "hakimetal-tests: %zu test(s), %d failure(s)\n", g_tests.size(), g_failures);
    std::fflush(stderr);
    return g_failures == 0 ? 0 : 1;
}
