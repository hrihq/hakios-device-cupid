#ifndef HAKIMETAL_COMMAND_BUFFER_H
#define HAKIMETAL_COMMAND_BUFFER_H

// A recorded sequence of commands, and the render encoder used inside a render pass.
//
// The frontend owns the barrier rules here: if the backend reports untracked_resources = false, every
// read-after-write the frontend performs must be preceded by a barrier the frontend issues. The
// backend is told about them; it never infers them.

#include "hakimetal/backend.h"
#include "hakimetal/buffer.h"
#include "hakimetal/render_pipeline.h"
#include "hakimetal/texture.h"

#include <array>
#include <memory>

namespace hakimetal {

struct RenderPassAttachmentDescriptor {
    std::shared_ptr<IBackendTexture> texture;   // backend handle; the frontend's Texture exposes it
    LoadAction load_action = LoadAction::Load;
    StoreAction store_action = StoreAction::Store;
    float clear_color[4] = {0.0f, 0.0f, 0.0f, 1.0f};
    float clear_depth = 1.0f;
    uint32_t clear_stencil = 0;
    bool used = false;
};

struct RenderPassDescriptor {
    // std::array rather than a C array: GCC 13 hits an internal compiler error gimplifying a C array
    // of aggregates whose members carry default initializers, which is what this used to be.
    std::array<RenderPassAttachmentDescriptor, 8> color_attachments = {};
    uint32_t color_attachment_count = 0;
    RenderPassAttachmentDescriptor depth_attachment = {};
    RenderPassAttachmentDescriptor stencil_attachment = {};
};

class RenderCommandEncoder {
public:
    RenderCommandEncoder() = default;
    RenderCommandEncoder(std::shared_ptr<IBackendRenderCommandEncoder> encoder)
        : encoder_(std::move(encoder)) {}

    bool valid() const { return encoder_ != nullptr; }

    Status set_render_pipeline(const RenderPipeline& pipeline);
    Status set_vertex_buffer(const Buffer& buffer, uint64_t offset, uint32_t index);
    Status set_fragment_texture(const Texture& texture, uint32_t index);
    Status set_blend_color(float red, float green, float blue, float alpha);
    Status set_depth_stencil_state(CompareFunction compare, bool write_enabled);
    Status draw(PrimitiveType type, uint32_t vertex_start, uint32_t vertex_count);
    Status draw_indexed(PrimitiveType type, uint32_t index_count, const Buffer& buffer,
                       uint64_t index_buffer_offset);
    Status end_encoding();

private:
    std::shared_ptr<IBackendRenderCommandEncoder> encoder_;
};

class CommandBuffer {
public:
    CommandBuffer() = default;
    CommandBuffer(std::shared_ptr<IBackendCommandBuffer> buffer, Capabilities capabilities)
        : buffer_(std::move(buffer)), capabilities_(capabilities) {}

    bool valid() const { return buffer_ != nullptr; }
    const Capabilities& capabilities() const { return capabilities_; }

    Result<RenderCommandEncoder> begin_render_pass(const RenderPassDescriptor& descriptor);
    Status commit();
    Status wait_until_completed();

    // The frontend owns the barrier rules: it issues these, the backend never infers them.
    Status buffer_barrier(const Buffer& buffer, const BarrierDescriptor& descriptor);
    Status texture_barrier(const Texture& texture, const BarrierDescriptor& descriptor);

private:
    std::shared_ptr<IBackendCommandBuffer> buffer_;
    Capabilities capabilities_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_COMMAND_BUFFER_H
