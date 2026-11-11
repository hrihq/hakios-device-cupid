# HakiMetal

An experimental, backend-independent graphics API for HakiOS.

HakiMetal takes the object model of Apple's **documented** Metal concepts -- device, command queue,
command buffer, render pipeline, buffer, texture, fence, event -- and puts them behind a backend
interface, so that a backend can be Vulkan, something else, or nothing at all.

**HakiMetal is not Apple Metal.** No Metal source compiles against it unchanged, no Metal binary runs
on it, and nothing here claims otherwise. The class names, method names and object shapes are
HakiMetal's own; the concepts come from Apple's public documentation, which describes an API, not an
implementation.

**Vulkan is not assumed to exist.** The Adreno 730 in the Xiaomi 12 (cupid) is an Android part; Vulkan
on HakiOS would need a userspace driver that does not exist yet. The Vulkan backend loads the Vulkan
loader at runtime and reports what it finds. When Vulkan is absent it reports `available = false`, and
every operation returns `NotAvailable`. It never pretends.

**Nothing here writes GPU registers.** The Vulkan backend calls the Vulkan API or reports absence. The
Adreno 642L driver in HakiOS is not modified.

## Status

Phase 1: architecture, compatibility research and a prototype. The Vulkan backend detects Vulkan and
reports capabilities; it does not create a device. Shader translation is not implemented. All tests
run without a GPU and without Vulkan.

## Layout

| Path | What |
|---|---|
| `include/hakimetal/` | the frontend API and the backend interface |
| `src/` | the frontend, the registry, the null backend, the Vulkan backend |
| `tests/` | unit tests against a mock backend |
| `docs/architecture.md` | the three layers, the capability contract, the error model |
| `docs/metal-to-vulkan.md` | the Metal-to-Vulkan compatibility matrix |
| `docs/limitations.md` | what HakiMetal does not do |

## Build and test

```
cmake -S hakimetal -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
```

The tests need no GPU and no Vulkan; the mock backend records calls and returns configured results.

## Design in one paragraph

An application holds a `Device` and creates objects from it. Every object forwards to the backend it
came from. Before translating an operation, the frontend checks the backend's `Capabilities`; a
capability the backend does not have yields `Status::Unsupported`, not a silent fallback. Three
things are the frontend's responsibility because Vulkan will not do them: memory placement and hazard
barriers, the shader translation path, and honest feature reporting. Those three are the capability
contract's reason to exist.

## Phase 2

A Vulkan backend that creates a real instance and device, queries device-level capabilities, and
implements the resource mappings the matrix marks as direct equivalents. It requires Vulkan to exist
on the target; until it does, the backend reports absence and the tests keep running without it.
