# HakiMetal Phase 1 -- audit

Review of the Phase 1 code at commit `a8acd30`, against the API contract, resource lifetime, error
propability, capability validation, thread safety and build portability. Findings by severity, each
with what was changed and the regression test that guards it.

**Nothing here changes hardware behaviour.** No register is touched, no Vulkan runtime is implemented,
no shader translator is added, and the Adreno 642L driver is untouched.

---

## Critical

None. No memory-safety defect that a caller can reach in normal use was found: every resource is a
`shared_ptr`, no raw `new`/`delete` exists, and no pointer outlives its owner in the paths the tests
exercise.

## High

### H1 -- the render pass descriptor crossed the backend boundary as `void*`

`IBackendCommandBuffer::begin_render_pass(const void* descriptor)` handed the backend an untyped
pointer. The real type lived in `command_buffer.h`, which `backend.h` cannot include without a cycle,
so a backend had to guess the pointee. A wrong guess is undefined behaviour, and the compiler cannot
catch it.

**Fix:** `RenderPassAttachmentDescriptor` and `RenderPassDescriptor` moved into `backend.h`, next to
the interface that consumes them, and the signature is now
`begin_render_pass(const RenderPassDescriptor&)`.

**Regression test:** `the render pass descriptor reaches the backend typed` -- the mock records the
attachment count and clear colour it received and the test checks both.

### H2 -- the registry was not thread-safe

`Registry::instance()` is a process-wide singleton, and `register_backend`, `find`, `backend_names` and
`default_backend` read and wrote a `std::vector` with no lock. Concurrent registration and lookup is a
data race, which is exactly the use a registry exists for.

**Fix:** a `std::mutex` guards every public method. `find` and `default_backend` return a
`shared_ptr` copy, so the object stays alive after the lock is released.

**Regression tests:** `the registry takes its lock: concurrent registration and lookup do not crash`
(eight threads, 200 iterations each), plus a ThreadSanitizer job in CI.

## Medium

### M1 -- a default-constructed `Result` claimed success

`Result<T>()` set `status_ = Status::Ok` with a default-constructed value. A caller that forgot to
check got `if (result)` true and a plausible-looking empty handle -- `Buffer()` reports `valid() ==
false`, so it would have failed later and nowhere near the cause.

**Fix:** the default constructor sets `Status::NotAvailable`. Added `has_value()`.

**Regression test:** `a default-constructed Result is not a success`.

### M2 -- a backend answering `Ok` with a null handle was accepted

`Device::create_command_queue` wrapped whatever the backend returned. A backend that returned
`Result<shared_ptr<IBackendCommandQueue>>(nullptr)` -- which the mock did before it was fixed --
produced a frontend object with nothing behind it, and the failure surfaced as a null dereference
deep inside a later call.

**Fix:** every `Device::create_*` and `CommandQueue::create_command_buffer` checks for a null handle
and returns `Status::BackendError`.

**Regression test:** `a backend that answers Ok with a null handle is a BackendError, not an empty
object`.

### M3 -- `dlopen` was used without linking `${CMAKE_DL_LIBS}`

The Vulkan backend calls `dlopen`/`dlsym`. On glibc >= 2.34 those live in libc and the build works; on
older glibc and on some BSDs it needs `-ldl`. The CI only exercised GCC, so Clang portability was
unverified.

**Fix:** `target_link_libraries(hakimetal PUBLIC ${CMAKE_DL_LIBS})`; the CI now builds with GCC and
with Clang, and runs ThreadSanitizer.

**Regression:** the `clang` matrix entry and the `thread-sanitizer` job.

## Low

### L1 -- two sources for the same fact

`IBackend::supported_extensions()` and `IBackendDevice::supported_extensions()` both existed. The
frontend only uses the device's.

**Fix:** documented in `backend.h` -- the device's copy is the one tied to a live device, and the
frontend reports that one. Both are kept because an application may want to ask a backend before
creating a device.

### L2 -- `Result::value()` is callable on a failed Result

The reference is valid but refers to a default-constructed value.

**Fix:** documented on the method; `has_value()` makes the check explicit.

### L3 -- `Device::capabilities()` returns a reference into the device

A caller who keeps the reference past the device's lifetime has a dangling reference.

**Fix:** documented. Returning by value would copy a 32-byte struct on every call; the reference is
the better trade, provided the contract is stated.

### L4 -- `Event::register_handler` stores a handler it never calls

The handler is kept so a caller can poll, but the shape suggests a callback. The method returns
`Unsupported`, which is honest.

**Fix:** documented; unchanged, because inventing a callback mechanism would be inventing API
behaviour.

### L5 -- `begin_render_pass` uses `dynamic_pointer_cast`

That needs RTTI. A backend built with `-fno-rtti` will not link.

**Fix:** documented in `command_buffer.h`. Phase 1 does not build with `-fno-rtti`; if a HakiOS build
does, the cast becomes a `static_cast` with a backend-side type tag.

---

## What was checked and found sound

* **Ownership.** Every resource is a `shared_ptr`. No raw `new`/`delete`, no `malloc`/`free`. Handles
  share the implementation object and the last handle frees it. `Buffer`, `Texture`,
  `RenderPipeline`, `Fence` and `Event` hold no reference back to the device, so no cycle.
* **Destruction order.** `Device` holds `shared_ptr<IBackendDevice>`; a device outliving its objects
  is fine and so is the reverse.
* **Error propagation.** `NotAvailable` (no backend / no device), `Unsupported` (the backend exists
  but cannot do this) and `BackendError` (the backend misbehaved) are distinct and every frontend
  method propagates them without inventing a success.
* **Capability validation.** A backend's capabilities are read once and copied into every object it
  creates, so an object cannot disagree with its backend about what is possible. The Null backend
  reports `available = false`; the Vulkan backend reports `vulkan = false` when the loader is absent
  and never creates a device it cannot make.
* **No fabricated capability.** Nothing in the code sets a capability it has not verified: the
  Vulkan backend leaves every device-level feature `false` in Phase 1 rather than guessing.
* **Build.** GCC and Clang both build clean with `-Wall -Wextra -Wpedantic`; ThreadSanitizer is clean.

## Not checked

* Any Vulkan runtime behaviour -- Vulkan is not implemented here.
* Any Metal runtime behaviour -- no Apple platform.
* Real hardware: nothing in HakiMetal touches hardware.
