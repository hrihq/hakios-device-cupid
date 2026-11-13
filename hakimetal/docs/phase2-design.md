# HakiMetal Phase 2 -- design

**Status: design. Nothing here is implemented, and the one precondition -- Vulkan on the target -- does
not hold today.** This document says what Phase 2 builds, what it needs, what it reports, and which
milestones cannot be reached until the environment changes.

Phase 1's audit is in [audit-phase1.md](audit-phase1.md). The compatibility matrix that Phase 2 works
against is in [metal-to-vulkan.md](metal-to-vulkan.md).

---

## The precondition

Phase 2 is a **Vulkan backend that creates a real instance and device**. That needs Vulkan to exist on
the target. The Adreno 730 in the Xiaomi 12 (cupid) is an Android part; Vulkan on HakiOS would need a
userspace Vulkan driver that does not exist yet.

So the design is written now and the implementation waits. This is the same discipline as the rest of
the project: an environment that does not exist is recorded as absent, not assumed.

## What Phase 2 builds

```
hakimetal::vulkan
  VulkanInstance      one per process, created from the loader
  VulkanPhysicalDevice  selected by a rule the caller can override
  VulkanDevice          a VkDevice plus the queue families it was given
  VulkanCommandPool     a pool per queue family
  VulkanBuffer          a VkBuffer + its VkDeviceMemory + its placement
  VulkanImage           a VkImage + VkImageView + VkDeviceMemory
  VulkanPipeline        a VkPipeline and its VkPipelineLayout
  VulkanFence           a VkFence
  VulkanSemaphore       a timeline or binary semaphore, chosen by what the device supports
```

Each type implements the corresponding `IBackend*` interface from Phase 1. Nothing new is added to the
frontend: the frontend already knows how to talk to a backend, and Phase 2 is a backend.

### The five jobs

1. **Instance creation.** Load the Vulkan loader (Phase 1 already does this), create an instance, and
   report the API version. Surface extensions are recorded, not guessed.
2. **Physical device selection.** Enumerate physical devices, and pick by a documented rule: the
   discrete device if there is one, otherwise the first device whose type is not `OTHER`. The caller
   can override by name. The rule is stated in the report.
3. **Capability reporting.** Query the device and fill the `Capabilities` struct honestly:
   `VkPhysicalDeviceFeatures` for geometry/tessellation/compute, `VkPhysicalDeviceProperties` for
   limits and the API version, extension presence for the optional features (descriptor heap, mesh
   shader, ray tracing, dynamic rendering local read, sparse binding, device generated commands).
   **A feature the device does not report stays `false`.**
4. **Resource mapping.** Buffer, image and memory, using the memory types the device actually offers.
   Metal's `StorageMode` maps onto Vulkan memory property flags, and the mapping is the frontend's
   responsibility (see below).
5. **Submission.** Command pools, command buffers, pipeline barriers for the barriers the frontend
   issues, fences and semaphores.

## The memory model, which is the hard part

Phase 1's matrix marks three resource concepts as having **no direct equivalent**:

| Metal concept | Vulkan reality | Who owns it |
|---|---|---|
| `StorageMode.managed` | no managed mode; coherence is manual | the frontend |
| `StorageMode.shared` / `private` | `HOST_VISIBLE` / `DEVICE_LOCAL` memory types | the backend reports what exists |
| `HazardTrackingMode.tracked` | no automatic hazard tracking at all | the frontend |

Phase 2's rule, unchanged from Phase 1:

* the **backend** reports which memory types exist and which features are present;
* the **frontend** decides placement and emits every barrier;
* if the device has no host-visible memory for a `Shared` resource, the backend reports
  `available = false` for that placement and the caller gets `Unsupported` -- **the frontend never
  silently degrades a resource to a different placement**.

`managed_storage` stays `false` until a backend can prove otherwise. A Vulkan device cannot prove it,
so Phase 2 reports `false`, and the frontend's rule applies: the application must stage explicitly.

## Capability reporting, concretely

| Capability | Source | Phase 2 |
|---|---|---|
| `vulkan_api_version` | `vkEnumerateInstanceVersion` / `VkPhysicalDeviceProperties::apiVersion` | query |
| `geometry_shaders` | `VkPhysicalDeviceFeatures::geometryShader` | query |
| `tessellation` | `VkPhysicalDeviceFeatures::tessellationShader` | query |
| `compute` | a queue family with `QUEUE_COMPUTE_BIT` | query |
| `max_texture_dimension` | `VkPhysicalDeviceLimits::maxImageDimension2D` | query |
| `max_buffer_length` | `VkPhysicalDeviceLimits::maxStorageBufferRange` | query |
| `descriptor_heap` | `VK_EXT_descriptor_heap` | extension |
| `argument_buffers` | descriptor heap **and** buffer device address | extension |
| `tile_shaders` | `VK_KHR_dynamic_rendering_local_read` | extension |
| `mesh_shaders` | `VK_EXT_mesh_shader` | extension |
| `ray_tracing` | `VK_KHR_ray_tracing_pipeline` | extension |
| `indirect_commands` | `VK_EXT_device_generated_commands` | extension |
| `sparse_textures` | `VK_KHR_sparse_binding` | extension |
| `untracked_resources` | always `false` -- Vulkan never tracks automatically | fixed |
| `managed_storage` | always `false` -- Vulkan has no managed mode | fixed |
| `shader_translation` | a translation path the backend can actually run | `false` in Phase 2 |

The last row is deliberate: **Phase 2 does not add a shader translator.** The frontend defines no
shader source format and the backend accepts none, so `RenderPipeline` creation stays
`Unsupported`. That is the honest state and the next phase's problem.

## What Phase 2 does not do

* no shader translation -- `RenderPipeline` stays unsupported;
* no tile-shader, mesh-shader or ray-tracing implementation -- those are reported as extensions and
  nothing more;
* no parallel render encoding -- Vulkan has no equivalent;
* no argument-buffer emulation -- a backend that reports `argument_buffers = false` rejects the
  feature;
* no claim that any of it works on a phone.

## Testing without a Vulkan driver

The backend's logic must be testable where Vulkan does not exist. Three layers:

1. **A mock loader.** The backend resolves Vulkan functions through an interface that can be backed
   by a fake. The fake records calls and returns configured results, so the device-selection rule,
   the capability mapping and the error paths are unit-testable with no driver.
2. **The existing mock backend.** The frontend's tests keep running unchanged, because the frontend
   does not know which backend it talks to.
3. **The real loader, when present.** The same code path runs against a real driver; the CI runner has
   no Vulkan, so CI exercises the fake and reports the real loader as absent.

This is the same shape as Phase 1's `NullBackend` and `VulkanBackend`: the detection path is real, the
execution path is testable without the environment.

## Milestones

| Milestone | Needs | Verifiable now? |
|---|---|---|
| M1 -- instance and physical device enumeration | a Vulkan loader | no |
| M2 -- device creation and queue family selection | a loader and a driver | no |
| M3 -- capability reporting against a real device | a loader and a driver | no |
| M4 -- buffer and image creation against a real device | M3 | no |
| M5 -- command submission against a real device | M4 | no |
| M6 -- shader translation | a translator, and a driver | no |

M1 through M6 are all blocked on the same thing: a Vulkan implementation for the target. **None of them
is claimed, and none of them can be verified by a successful build.**

## What would unblock it

| Blocker | What changes it |
|---|---|
| no Vulkan loader on the target | a Vulkan implementation HakiOS can load, or a port of one |
| no device driver | a userspace Vulkan driver for the Adreno 730 that runs on HakiOS |
| no shader path | a translator from a defined frontend source to SPIR-V |

Until one of those lands, the Vulkan backend's job is to report absence honestly -- which Phase 1
already does, and which Phase 2 keeps doing.
