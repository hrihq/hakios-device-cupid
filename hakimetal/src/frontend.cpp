#include "hakimetal/hakimetal.h"

namespace hakimetal {

const char* status_message(Status status) {
    switch (status) {
        case Status::Ok: return "ok";
        case Status::Unsupported: return "unsupported by this backend";
        case Status::NotAvailable: return "backend not available";
        case Status::InvalidArgument: return "invalid argument";
        case Status::OutOfMemory: return "out of memory";
        case Status::BackendError: return "backend error";
    }
    return "unknown status";
}

// -------------------------------------------------------------------------------------------
// Device
// -------------------------------------------------------------------------------------------

Result<CommandQueue> Device::create_command_queue(const CommandQueueDescriptor& descriptor) {
    if (!device_) return Result<CommandQueue>(Status::NotAvailable);
    auto result = device_->create_command_queue(descriptor);
    if (!result) return Result<CommandQueue>(result.status());
    return Result<CommandQueue>(CommandQueue(result.value(), capabilities()));
}

Result<Buffer> Device::create_buffer(const BufferDescriptor& descriptor) {
    if (!device_) return Result<Buffer>(Status::NotAvailable);
    auto result = device_->create_buffer(descriptor);
    if (!result) return Result<Buffer>(result.status());
    return Result<Buffer>(Buffer(result.value(), capabilities()));
}

Result<Texture> Device::create_texture(const TextureDescriptor& descriptor) {
    if (!device_) return Result<Texture>(Status::NotAvailable);
    auto result = device_->create_texture(descriptor);
    if (!result) return Result<Texture>(result.status());
    return Result<Texture>(Texture(result.value(), capabilities()));
}

Result<RenderPipeline> Device::create_render_pipeline(const RenderPipelineDescriptor& descriptor) {
    if (!device_) return Result<RenderPipeline>(Status::NotAvailable);
    auto result = device_->create_render_pipeline(descriptor);
    if (!result) return Result<RenderPipeline>(result.status());
    return Result<RenderPipeline>(RenderPipeline(result.value(), capabilities()));
}

Result<Fence> Device::create_fence(const FenceDescriptor& descriptor) {
    if (!device_) return Result<Fence>(Status::NotAvailable);
    auto result = device_->create_fence(descriptor);
    if (!result) return Result<Fence>(result.status());
    return Result<Fence>(Fence(result.value()));
}

Result<Event> Device::create_event(const EventDescriptor& descriptor) {
    if (!device_) return Result<Event>(Status::NotAvailable);
    auto result = device_->create_event(descriptor);
    if (!result) return Result<Event>(result.status());
    return Result<Event>(Event(result.value()));
}

// -------------------------------------------------------------------------------------------
// CommandQueue
// -------------------------------------------------------------------------------------------

Result<CommandBuffer> CommandQueue::create_command_buffer() {
    if (!queue_) return Result<CommandBuffer>(Status::NotAvailable);
    auto result = queue_->create_command_buffer();
    if (!result) return Result<CommandBuffer>(result.status());
    return Result<CommandBuffer>(CommandBuffer(result.value(), capabilities_));
}

// -------------------------------------------------------------------------------------------
// CommandBuffer
// -------------------------------------------------------------------------------------------

Result<RenderCommandEncoder> CommandBuffer::begin_render_pass(const RenderPassDescriptor& descriptor) {
    if (!buffer_) return Result<RenderCommandEncoder>(Status::NotAvailable);
    auto result = buffer_->begin_render_pass(&descriptor);
    if (!result) return Result<RenderCommandEncoder>(result.status());
    auto encoder = std::dynamic_pointer_cast<IBackendRenderCommandEncoder>(result.value());
    if (!encoder) return Result<RenderCommandEncoder>(Status::BackendError);
    return Result<RenderCommandEncoder>(RenderCommandEncoder(encoder));
}

Status CommandBuffer::commit() {
    return buffer_ ? buffer_->commit() : Status::NotAvailable;
}

Status CommandBuffer::wait_until_completed() {
    return buffer_ ? buffer_->wait_until_completed() : Status::NotAvailable;
}

Status CommandBuffer::buffer_barrier(const Buffer& buffer, const BarrierDescriptor& descriptor) {
    if (!buffer_) return Status::NotAvailable;
    if (!buffer.valid()) return Status::InvalidArgument;
    return buffer_->buffer_barrier(buffer.handle(), descriptor);
}

Status CommandBuffer::texture_barrier(const Texture& texture, const BarrierDescriptor& descriptor) {
    if (!buffer_) return Status::NotAvailable;
    if (!texture.valid()) return Status::InvalidArgument;
    return buffer_->texture_barrier(texture.handle(), descriptor);
}

// -------------------------------------------------------------------------------------------
// RenderCommandEncoder
// -------------------------------------------------------------------------------------------

Status RenderCommandEncoder::set_render_pipeline(const RenderPipeline& pipeline) {
    if (!encoder_) return Status::NotAvailable;
    if (!pipeline.valid()) return Status::InvalidArgument;
    return encoder_->set_render_pipeline(pipeline.handle());
}

Status RenderCommandEncoder::set_vertex_buffer(const Buffer& buffer, uint64_t offset, uint32_t index) {
    if (!encoder_) return Status::NotAvailable;
    if (!buffer.valid()) return Status::InvalidArgument;
    return encoder_->set_vertex_buffer(buffer.handle(), offset, index);
}

Status RenderCommandEncoder::set_fragment_texture(const Texture& texture, uint32_t index) {
    if (!encoder_) return Status::NotAvailable;
    if (!texture.valid()) return Status::InvalidArgument;
    return encoder_->set_fragment_texture(texture.handle(), index);
}

Status RenderCommandEncoder::set_blend_color(float red, float green, float blue, float alpha) {
    return encoder_ ? encoder_->set_blend_color(red, green, blue, alpha) : Status::NotAvailable;
}

Status RenderCommandEncoder::set_depth_stencil_state(CompareFunction compare, bool write_enabled) {
    return encoder_ ? encoder_->set_depth_stencil_state(compare, write_enabled) : Status::NotAvailable;
}

Status RenderCommandEncoder::draw(PrimitiveType type, uint32_t vertex_start, uint32_t vertex_count) {
    return encoder_ ? encoder_->draw(type, vertex_start, vertex_count) : Status::NotAvailable;
}

Status RenderCommandEncoder::draw_indexed(PrimitiveType type, uint32_t index_count, const Buffer& buffer,
                                         uint64_t index_buffer_offset) {
    if (!encoder_) return Status::NotAvailable;
    if (!buffer.valid()) return Status::InvalidArgument;
    return encoder_->draw_indexed(type, index_count, buffer.handle(), index_buffer_offset);
}

Status RenderCommandEncoder::end_encoding() {
    return encoder_ ? encoder_->end_encoding() : Status::NotAvailable;
}

}   // namespace hakimetal
