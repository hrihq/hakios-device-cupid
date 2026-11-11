#ifndef HAKIMETAL_TYPES_H
#define HAKIMETAL_TYPES_H

// HakiMetal -- types shared by the frontend and the backends.
//
// This is not Apple Metal. The concepts here follow Apple's *documented* Metal object model; the
// names, the shapes and the behaviour are HakiMetal's own. Nothing in this file is copied from an
// Apple header, and nothing here claims Metal compatibility.
//
// Two concepts come from Metal's documentation and have no Vulkan equivalent: StorageMode's "managed"
// mode and HazardTrackingMode. They are carried here because an application thinks in them; whether a
// backend can honour them is a capability, not an assumption. See docs/metal-to-vulkan.md.

#include <array>
#include <cstdint>
#include <utility>

namespace hakimetal {

enum class Status {
    Ok,
    Unsupported,       // the backend does not provide this operation or feature
    NotAvailable,      // the backend is absent (no Vulkan, no device)
    InvalidArgument,   // the caller's descriptor was rejected
    OutOfMemory,
    BackendError,
};

const char* status_message(Status status);

// ---------------------------------------------------------------------------------------------
// Capabilities
// ---------------------------------------------------------------------------------------------

struct Capabilities {
    const char* backend_name = "null";
    bool available = false;

    bool vulkan = false;
    uint32_t vulkan_api_version = 0;

    bool geometry_shaders = false;
    bool tessellation = false;
    bool compute = false;

    // The two things Metal does for the application and Vulkan does not. See docs/architecture.md.
    bool untracked_resources = false;
    bool managed_storage = false;

    bool argument_buffers = false;
    bool descriptor_heap = false;
    bool tile_shaders = false;
    bool mesh_shaders = false;
    bool ray_tracing = false;
    bool indirect_commands = false;
    bool sparse_textures = false;

    // Shader path. No backend claims one until it can produce SPIR-V (or another Vulkan-consumable
    // format) from something the frontend accepts.
    bool shader_translation = false;

    uint32_t max_texture_dimension = 0;
    uint32_t max_buffer_length = 0;
};

// ---------------------------------------------------------------------------------------------
// Descriptors and enums
// ---------------------------------------------------------------------------------------------

// Metal's documented storage modes. "managed" means the platform keeps CPU and GPU copies coherent;
// a backend that cannot do that must report managed_storage = false.
enum class StorageMode {
    Shared,     // one copy, visible to both
    Managed,    // the platform keeps copies coherent
    Private,    // GPU-only
};

// Metal's documented hazard tracking modes. Vulkan never tracks automatically, so a backend that
// requires the frontend to emit every barrier reports untracked_resources = false.
enum class HazardTrackingMode {
    Tracked,
    Untracked,
};

enum class TextureFormat {
    Invalid,
    R8Unorm,
    R8Uint,
    R16Float,
    R16Uint,
    R32Float,
    R32Uint,
    RG8Unorm,
    RG16Float,
    RG32Float,
    RGBA8Unorm,
    RGBA8Unorm_sRGB,
    BGRA8Unorm,
    RGBA16Float,
    RGBA32Float,
    Depth32Float,
    Stencil8,
    Depth32Float_Stencil8,
};

enum class TextureUsage : uint32_t {
    None = 0,
    Read = 1u << 0,
    Write = 1u << 1,
    RenderTarget = 1u << 2,
    ShaderRead = Read,
    ShaderWrite = Write,
};

enum class TextureType {
    Texture1D,
    Texture2D,
    Texture2DArray,
    TextureCube,
    Texture3D,
};

enum class PrimitiveType {
    Point,
    Line,
    LineStrip,
    Triangle,
    TriangleStrip,
};

enum class LoadAction { Load, Clear, DontCare };

enum class StoreAction { Store, DontCare, MultisampleResolve };

enum class CompareFunction {
    Never, Less, Equal, LessEqual, Greater, NotEqual, GreaterEqual, Always,
};

enum class BlendFactor {
    Zero, One,
    SourceColor, OneMinusSourceColor,
    SourceAlpha, OneMinusSourceAlpha,
    DestinationColor, OneMinusDestinationColor,
    DestinationAlpha, OneMinusDestinationAlpha,
    BlendColor, OneMinusBlendColor,
    BlendAlpha, OneMinusBlendAlpha,
    SourceAlphaSaturated,
};

enum class BlendOperation { Add, Subtract, ReverseSubtract, Min, Max };

enum class Winding { Clockwise, CounterClockwise };

enum class CullMode { None, Front, Back };

// Metal's documented depth clip modes.
enum class DepthClipMode { Clip, Clamp };

enum class SamplerAddressMode { ClampToEdge, Repeat, MirrorRepeat, ClampToZero };
enum class SamplerMinMagFilter { Nearest, Linear };
enum class SamplerMipFilter { NotMipmapped, Nearest, Linear };

struct DeviceDescriptor {
    const char* label = "hakimetal";
};

struct CommandQueueDescriptor {
    const char* label = "hakimetal";
    uint32_t max_buffer_count = 64;
};

struct BufferDescriptor {
    uint64_t length = 0;
    StorageMode storage_mode = StorageMode::Shared;
    HazardTrackingMode hazard_tracking = HazardTrackingMode::Tracked;
    uint32_t usage = 0;   // backend-defined
};

struct TextureDescriptor {
    TextureType type = TextureType::Texture2D;
    TextureFormat format = TextureFormat::RGBA8Unorm;
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t depth = 1;
    uint32_t mipmap_level_count = 1;
    uint32_t sample_count = 1;
    StorageMode storage_mode = StorageMode::Private;
    HazardTrackingMode hazard_tracking = HazardTrackingMode::Tracked;
    TextureUsage usage = TextureUsage::ShaderRead;
};

struct SamplerDescriptor {
    SamplerMinMagFilter min_filter = SamplerMinMagFilter::Linear;
    SamplerMinMagFilter mag_filter = SamplerMinMagFilter::Linear;
    SamplerMipFilter mip_filter = SamplerMipFilter::NotMipmapped;
    SamplerAddressMode address_mode_s = SamplerAddressMode::ClampToEdge;
    SamplerAddressMode address_mode_t = SamplerAddressMode::ClampToEdge;
    SamplerAddressMode address_mode_r = SamplerAddressMode::ClampToEdge;
    CompareFunction compare_function = CompareFunction::Never;
    uint32_t max_anisotropy = 1;
    float lod_min_clamp = 0.0f;
    float lod_max_clamp = 340282346638528859811704183484516925440.0f;
};

struct RenderPipelineColorAttachmentDescriptor {
    TextureFormat format = TextureFormat::BGRA8Unorm;
    bool blending_enabled = false;
    BlendFactor source_rgb_blend_factor = BlendFactor::One;
    BlendFactor destination_rgb_blend_factor = BlendFactor::Zero;
    BlendOperation rgb_blend_operation = BlendOperation::Add;
    BlendFactor source_alpha_blend_factor = BlendFactor::One;
    BlendFactor destination_alpha_blend_factor = BlendFactor::Zero;
    BlendOperation alpha_blend_operation = BlendOperation::Add;
    uint8_t write_mask = 0x0F;
};

struct RenderPipelineDescriptor {
    const char* label = "hakimetal";
    const char* vertex_function_source = nullptr;
    const char* fragment_function_source = nullptr;
    bool shader_source_is_spir_v = false;
    std::array<RenderPipelineColorAttachmentDescriptor, 8> color_attachments = {};
    uint32_t color_attachment_count = 1;
    TextureFormat depth_attachment_format = TextureFormat::Invalid;
    TextureFormat stencil_attachment_format = TextureFormat::Invalid;
    PrimitiveType primitive_type = PrimitiveType::Triangle;
    Winding winding = Winding::CounterClockwise;
    CullMode cull_mode = CullMode::None;
    DepthClipMode depth_clip_mode = DepthClipMode::Clip;
    CompareFunction depth_compare_function = CompareFunction::Always;
    bool depth_write_enabled = false;
    uint32_t sample_count = 1;
};

struct FenceDescriptor {
    bool initially_signaled = false;
};

struct EventDescriptor {
    uint64_t initial_value = 0;
};

// A memory barrier the frontend issues. Vulkan needs these explicitly; Metal tracks hazards for
// "tracked" resources and does not. A backend that reports untracked_resources = false means the
// frontend must issue every barrier itself, and this is how it does.
struct BarrierDescriptor {
    uint32_t source_stage = 0;
    uint32_t destination_stage = 0;
    uint32_t source_access = 0;
    uint32_t destination_access = 0;
};

// ---------------------------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------------------------

// Every operation returns one of these. There is no silent fallback and no emulated success: a
// backend that cannot do something returns Unsupported or NotAvailable, and the caller can tell
// which.
template <typename T>
class Result {
public:
    // A default-constructed Result is not a success: it carries no value. Defaulting to Ok was a
    // footgun -- a caller that forgot to check got a plausible-looking empty handle.
    Result() : status_(Status::NotAvailable) {}
    Result(Status status) : status_(status) {}   // NOLINT(google-explicit-constructor)
    Result(T value) : status_(Status::Ok), value_(std::move(value)) {}   // NOLINT

    bool ok() const { return status_ == Status::Ok; }
    bool has_value() const { return ok(); }
    explicit operator bool() const { return ok(); }
    Status status() const { return status_; }
    const char* message() const { return status_message(status_); }

    // Only valid when ok() is true. Calling value() on a failed Result returns a
    // default-constructed T; callers must check first.
    const T& value() const { return value_; }
    T& value() { return value_; }

private:
    Status status_;
    T value_{};
};

// A Result with no payload.
using StatusResult = Result<bool>;

}   // namespace hakimetal

#endif   // HAKIMETAL_TYPES_H
