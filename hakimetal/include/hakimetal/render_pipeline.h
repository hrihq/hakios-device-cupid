#ifndef HAKIMETAL_RENDER_PIPELINE_H
#define HAKIMETAL_RENDER_PIPELINE_H

// A render pipeline state.

#include "hakimetal/backend.h"

#include <memory>

namespace hakimetal {

class RenderPipeline {
public:
    RenderPipeline() = default;
    RenderPipeline(std::shared_ptr<IBackendRenderPipeline> pipeline, Capabilities capabilities)
        : pipeline_(std::move(pipeline)), capabilities_(capabilities) {}

    bool valid() const { return pipeline_ != nullptr; }
    const RenderPipelineDescriptor& descriptor() const {
        static const RenderPipelineDescriptor empty{};
        return pipeline_ ? pipeline_->descriptor() : empty;
    }
    const Capabilities& capabilities() const { return capabilities_; }

    std::shared_ptr<IBackendRenderPipeline> handle() const { return pipeline_; }

private:
    std::shared_ptr<IBackendRenderPipeline> pipeline_;
    Capabilities capabilities_;
};

}   // namespace hakimetal

#endif   // HAKIMETAL_RENDER_PIPELINE_H
