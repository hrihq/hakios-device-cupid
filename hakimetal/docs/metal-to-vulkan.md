# Metal-to-Vulkan compatibility matrix

**This is a research document, not a design commitment.** It records which publicly documented Metal
concepts have a Vulkan equivalent, which have only a partial one, and which have none. Every row cites
the source it came from.

Two caveats that shape the whole table:

* **Vulkan is not assumed to exist on the target.** The Adreno 730 in the Xiaomi 12 (cupid) is an
  Android part; Vulkan on HakiOS would come from a userspace driver that does not exist yet. Nothing
  here says Vulkan is available, and the architecture treats it as a runtime discovery.
* **Metal is not assumed to be reproducible.** Apple publishes the concepts, not the implementation.
  A Vulkan backend can cover the *concept*; it cannot cover the ABI, the tile-based deferred renderer's
  behaviour, or Apple's shader language.

Sources: Apple's Metal documentation at `developer.apple.com/documentation/metal`, and the Khronos
Vulkan specification and extension reference pages at `registry.khronos.org/vulkan` and
`docs.vulkan.org`. Apple's "Understanding the Metal 4 core API" notes that Metal 4 introduces `MTL4`
types that are "completely independent from the original `MTL` types they replace".

---

## 1. Core objects

| Metal concept | Vulkan equivalent | Direct equivalent | Gaps and notes |
|---|---|---|---|
| `MTLDevice` | `VkDevice` (and `VkPhysicalDevice`) | ✓ | Vulkan splits the physical device from the logical device; Metal does not. A backend must create both. |
| `MTLCommandQueue` / `MTL4CommandQueue` | `VkQueue` | ✓ | Metal exposes one queue per device per family; Vulkan exposes multiple queues with explicit flags and multiple families. |
| `MTLCommandBuffer` / `MTL4CommandBuffer` | `VkCommandBuffer` | ✓ | Both are a recorded sequence of commands. Metal 4's `MTL4CommandBuffer` is a separate type from `MTLCommandBuffer`. |
| `MTLCommandEncoder` | `VkCommandBuffer` with a bind point | ✓ | Metal splits encoders by pass (render, compute, blit, parallel); Vulkan uses one command buffer with explicit pipeline and render-pass state. |
| `MTLLibrary` / `MTLFunction` | none | — | Vulkan has no shader library object. Shaders arrive as SPIR-V modules. A Metal-shaped frontend needs a translation step; see section 5. |
| `MTLHeap` / `MTLHeapDescriptor` | none | — | Vulkan has no heap object; memory is allocated from `VkMemoryRequirements` against `VkDeviceMemory`. |
| `MTLResidencySet` | none | — | Residency management is an explicit application duty in Vulkan. |

## 2. Command encoding

| Metal concept | Vulkan equivalent | Direct equivalent | Gaps and notes |
|---|---|---|---|
| render pass descriptor, load/store actions | `VkRenderPass` attachments with `VkAttachmentLoadOp` / `VkAttachmentStoreOp` | ✓ | Direct mapping. Vulkan's render pass also carries subpass dependencies Metal does not have. |
| `MTLRenderCommandEncoder` | `vkCmdBeginRenderPass` + draw commands | ✓ | |
| `MTLComputeCommandEncoder` | `vkCmdBindPipeline(COMPUTE)` + `vkCmdDispatch` | ✓ | |
| `MTLBlitCommandEncoder` | `vkCmdCopyImage` / `vkCmdCopyBuffer` / `vkCmdBlitImage` | ✓ | |
| `MTLParallelRenderCommandEncoder` | none | — | No Vulkan equivalent for splitting one render pass across threads. |
| `MTLIndirectCommandBuffer` | `VkIndirectExecutionSetEXT` (`VK_EXT_device_generated_commands`, registered extension 573) | — | Close in intent but not in shape: Vulkan's extension generates commands on the device from an indirect commands layout; Metal's object is a buffer the CPU or GPU encodes. |
| visibility result buffer | none | — | Occlusion queries exist in Vulkan (`VkQueryPool`), but Metal's visibility-result-buffer workflow has no direct counterpart. |

## 3. Resources

| Metal concept | Vulkan equivalent | Direct equivalent | Gaps and notes |
|---|---|---|---|
| `MTLBuffer` | `VkBuffer` | ✓ | |
| `MTLTexture`, `MTLTextureDescriptor` | `VkImage` + `VkImageView` + `VkSampler` | ✓ | Vulkan splits the image, the view and the sampler; Metal combines them. |
| `MTLResourceOptions.storageMode` (shared / managed / private) | memory property flags (`VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT`, `DEVICE_LOCAL_BIT`) | — | Metal's **managed** mode needs an explicit blit to keep CPU and GPU copies coherent on some platforms. Vulkan has no managed mode: coherence is the application's job, and there is no blit step that does it for you. |
| `MTLResourceOptions.hazardTrackingMode` (tracked / untracked) | explicit barriers (`VkBufferMemoryBarrier`, `VkImageMemoryBarrier`) | — | Metal tracks hazards for `tracked` resources; Vulkan has no per-resource automatic hazard tracking at all. The frontend must emit barriers itself. |
| `MTLResourceOptions.cpuCacheMode` | memory property flags | ✓ | |
| texture view pools (`MTLTextureViewPool`) | none | — | Vulkan allocates views individually. |
| sparse textures | `VK_KHR_sparse_binding` | — | Exists in Vulkan, but as an optional device feature with different semantics. |
| argument buffers (`MTLArgumentEncoder`) | `VK_EXT_descriptor_buffer` (extension 317) or `VK_EXT_descriptor_heap` (extension 136) | — | Neither is a direct match. `VK_EXT_descriptor_buffer` is **deprecated by** `VK_EXT_descriptor_heap`; the latter gives one sampler heap and one resource heap whose memory both the CPU and GPU can access. Metal's argument buffer is a buffer a shader indexes. |

## 4. Render pipeline

| Metal concept | Vulkan equivalent | Direct equivalent | Gaps and notes |
|---|---|---|---|
| `MTLRenderPipelineState`, `MTLRenderPipelineDescriptor` | `VkPipeline` (graphics) | ✓ | Vulkan separates the pipeline layout, the render pass compatibility and the pipeline; Metal folds them into one descriptor. |
| vertex descriptor (`MTLVertexDescriptor`) | `VkPipelineVertexInputStateCreateInfo` | ✓ | |
| function specialization (function constants) | specialization constants (`VkSpecializationInfo`) | ✓ | Both are compile-time constants baked into a pipeline variant. |
| `MTLDepthStencilState` | `VkPipelineDepthStencilStateCreateInfo` | ✓ | |
| blending / color attachments | `VkPipelineColorBlendAttachmentState` | ✓ | |
| tessellation | `VkPipelineTessellationStateCreateInfo` | ✓ | Optional device feature in Vulkan. |
| geometry shaders | `VK_EXT_geometry_shader` / `VK_NV_geometry_shader_passthrough` | — | Optional and not universally available. |
| tile shaders | `VK_KHR_dynamic_rendering_local_read` (extension 233) | — | The extension "enables reads from attachments and resources written by previous fragment shaders within a dynamic render pass". That is the Vulkan mechanism for tile-local work, but the programming model is not Metal's tile shader. |
| mesh shaders | `VK_EXT_mesh_shader` | — | Exists, different model (task + mesh stages). |
| ray tracing | `VK_KHR_ray_tracing_pipeline`, `VK_KHR_acceleration_structure` | — | Exists, different model (SBTs, acceleration structures). |

## 5. Shaders

| Metal concept | Vulkan equivalent | Direct equivalent | Gaps and notes |
|---|---|---|---|
| Metal Shading Language | SPIR-V | — | A Vulkan backend needs a translation step from whatever the frontend accepts to SPIR-V. The Metal Shading Language specification is published by Apple; SPIR-V is Khronos's. They are not interchangeable. |
| `MTLFunction` with function constants | `VkPipelineShaderStageCreateInfo` + specialization constants | ✓ | The constant mechanism maps; the source language does not. |
| argument buffers referenced from shader | descriptor buffers / descriptor heaps | — | Different binding model (see section 3). |
| GPU-encoded argument buffers | device-generated commands | — | See section 2. |

## 6. Synchronization

| Metal concept | Vulkan equivalent | Direct equivalent | Gaps and notes |
|---|---|---|---|
| `MTLFence`, `waitForFence:`, `updateFence:` | `VkFence` | ✓ | `VkFence` is host-visible and host-waited. |
| `MTLSharedEvent`, `MTLSharedEventListener` | `VkSemaphore` (timeline, `VK_KHR_timeline_semaphore`) | — | The shared event's `notify(atValue:block:)` is a **CPU-side** callback when a value is reached. Vulkan timeline semaphores signal a 64-bit value but have no CPU callback; the host waits or spins. |
| producer/consumer barriers | `VkBufferMemoryBarrier` / `VkImageMemoryBarrier` with stage and access masks | ✓ | Vulkan's `VK_KHR_synchronization2` gives the stage/access form that maps most directly. |
| `MTLStages` / `MTLRenderStages` / `MTLBarrierScope` | `VkPipelineStageFlagBits`, `VkAccessFlagBits` | ✓ | |
| `hazardTrackingMode` untracked resources | no equivalent | — | See section 3: Vulkan never tracks automatically. |

## 7. Summary

| Area | Concepts with a direct equivalent | Concepts with only a partial or optional one | Concepts with none |
|---|---|---|---|
| Core objects | 4 | 0 | 3 |
| Command encoding | 4 | 1 | 2 |
| Resources | 3 | 5 | 1 |
| Render pipeline | 6 | 4 | 0 |
| Shaders | 1 | 2 | 1 |
| Synchronization | 3 | 2 | 0 |

**What this means for the architecture.** The object model maps well; the memory model, the shader
source and the synchronization *mechanisms* do not. A backend-independent frontend can hold the
object model and the recording flow, but three things must be explicit rather than translated:

1. **Memory placement and hazard tracking** -- the frontend must own the barrier and staging rules,
   because Vulkan will not.
2. **Shader translation** -- the frontend must define what it accepts and the backend must report
   whether it can produce SPIR-V from it.
3. **Feature reporting** -- a feature the backend cannot provide must be reported as unavailable, not
   emulated silently.

Those three become the backend's `capabilities()` contract, which is what the architecture is built
around. See [architecture.md](architecture.md).
