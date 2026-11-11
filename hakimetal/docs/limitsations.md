# HakiMetal limitations

The list of things HakiMetal does not do, and what would change each. This is the honest half of the
project. The other half is [metal-to-vulkan.md](metal-to-vulkan.md).

## Not Apple Metal

* **Not a drop-in.** No Metal source compiles against HakiMetal unchanged, and no Metal binary runs on
  it. The class names, the method names and the object shapes are HakiMetal's own. Apple publishes
  concepts; it does not publish an implementation to match.
* **Not a claim of compatibility.** Nothing here says "Metal compatible" in the sense Apple uses it.
  Where a Metal concept appears, it appears because Apple documents it, and the mapping is HakiMetal's.
* **Metal 4 is a separate type family.** Apple's own documentation notes that Metal 4's `MTL4` types
  are "completely independent from the original `MTL` types they replace". Even the target of the
  comparison is not one thing.

## No Vulkan is assumed

* **Vulkan may not exist on the target.** The Adreno 730 in the Xiaomi 12 (cupid) is an Android part.
  Vulkan on HakiOS would need a userspace driver that does not exist yet. `VulkanBackend` loads Vulkan
  at runtime and reports `available = false` when it is absent; it does not create a device and does
  not pretend otherwise.
* **No GPU register writes.** Nothing in this project writes hardware directly. The Vulkan backend
  calls the Vulkan API or reports absence.
* **The Adreno 642L driver is untouched.** HakiOS already has a working Adreno 642L path for a
  different phone. This project does not modify it, and the device repository carries no GPU driver of
  its own.
* **Adreno 730 bring-up is not a precondition.** The GPU work on this device (see the device
  repository's `gpu/` and `docs/gpu-*.md`) is separate and earlier. HakiMetal can be designed and
  tested without it.

## What the backend cannot do yet

* **No shader translation.** The frontend defines no shader source format and the backend accepts
  none. `RenderPipeline` creation is unsupported until a backend reports a shader path.
* **No memory model promises.** If a backend reports `managed_storage = false` and
  `untracked_resources = false` -- as the Null and Mock backends do -- the frontend must emit every
  barrier and must not promise CPU/GPU coherence. A real Vulkan backend will report what the device
  supports, which may be less than Metal's model.
* **No argument-buffer parity.** Vulkan's `VK_EXT_descriptor_buffer` is deprecated by
  `VK_EXT_descriptor_heap`, and neither matches Metal's shader-indexed argument buffer. A backend
  that reports `argument_buffers = false` must reject the feature, not emulate it.
* **No tile-shader parity.** `VK_KHR_dynamic_rendering_local_read` is the Vulkan mechanism for
  tile-local reads, not a tile-shader programming model.
* **No parallel render encoding.** Vulkan has no equivalent of Metal's parallel render command
  encoder.

## What this means for an application

An application written against HakiMetal gets:

* an object model shaped like documented Metal concepts;
* a backend it can query, with an honest answer about every feature;
* an error, not a silent failure, when a feature is missing.

It does not get Metal, and it does not get Vulkan unless Vulkan is actually present.

## What would change these limits

| Limit | What would change it |
|---|---|
| Vulkan on the target | a userspace Vulkan driver for the device, or a Vulkan implementation HakiOS can load |
| shader translation | a backend that accepts a defined source and produces SPIR-V |
| memory model | a backend that reports `managed_storage` or `untracked_resources` honestly |
| argument buffers | a Vulkan extension that matches the model, or a frontend that accepts descriptor sets instead |
