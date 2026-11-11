#ifndef HAKIMETAL_TEXTURE_H
#define HAKIMETAL_TEXTURE_H

// A texture handle. Metal combines the image, the view and the sampler; Vulkan separates them, and
// the backend decides how it stores them.

#include "hakimetal/backend.h"

#include <memory>

namespace hakimetal {

class Texture {
public:
    Texture() = default;
    Texture(std::shared_ptr<IBackendTexture> texture, Capabilities capabilities)
        : texture_(std::move(texture)), capabilities_(capabilities) {}

    bool valid() const { return texture_ != nullptr; }
    const TextureDescriptor& descriptor() const {
        static const TextureDescriptor empty{};
        return texture_ ? texture_->descriptor() : empty;
    }
    const Capabilities& capabilities() const { return capabilities_; }

    std::shared_ptr<IBackendTexture> handle() const { return texture_; }

private:
    std::shared_ptr<IBackendTexture> texture_;
    Capabilities capabilities_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_TEXTURE_H
