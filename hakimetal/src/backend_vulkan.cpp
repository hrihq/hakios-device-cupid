#include "hakimetal/hakimetal.h"

#include <string>
#include <vector>

#if defined(__unix__) || defined(__APPLE__)
#include <dlfcn.h>
#endif
#if defined(_WIN32)
#include <windows.h>
#endif

// The Vulkan backend, Phase 1 scope: detection and honest reporting.
//
// It loads the Vulkan loader at runtime and reports what it finds. It does NOT create a device, does
// NOT create an instance in capabilities(), and does NOT write any GPU register. Device-level
// capability reporting and device creation are later phases, because they need a real Vulkan
// implementation and a real driver -- and neither is assumed to exist here.

namespace hakimetal {
namespace {

using EnumerateInstanceVersionFn = int32_t (*)(uint32_t* version);
using EnumerateInstanceExtensionPropertiesFn = int32_t (*)(const char* layer, uint32_t* count,
                                                           void* properties);

struct VulkanLoader {
    void* handle = nullptr;
    EnumerateInstanceVersionFn enumerate_instance_version = nullptr;
    EnumerateInstanceExtensionPropertiesFn enumerate_instance_extensions = nullptr;

    ~VulkanLoader() {
#if defined(__unix__) || defined(__APPLE__)
        if (handle) dlclose(handle);
#endif
#if defined(_WIN32)
        if (handle) FreeLibrary(static_cast<HMODULE>(handle));
#endif
    }
};

// Loads the Vulkan loader, or returns false. This is the whole "is Vulkan there" question; nothing
// here assumes an Adreno 730 or any particular driver.
bool load_vulkan(VulkanLoader& loader) {
#if defined(__unix__) || defined(__APPLE__)
    const char* names[] = {"libvulkan.so.1", "libvulkan.so"};
    for (const char* name : names) {
        loader.handle = dlopen(name, RTLD_NOW | RTLD_LOCAL);
        if (loader.handle) break;
    }
    if (!loader.handle) return false;
    void* sym_version = dlsym(loader.handle, "vkEnumerateInstanceVersion");
    void* sym_extensions = dlsym(loader.handle, "vkEnumerateInstanceExtensionProperties");
    loader.enumerate_instance_version =
        reinterpret_cast<EnumerateInstanceVersionFn>(sym_version);
    loader.enumerate_instance_extensions =
        reinterpret_cast<EnumerateInstanceExtensionPropertiesFn>(sym_extensions);
    return loader.enumerate_instance_version != nullptr;
#elif defined(_WIN32)
    loader.handle = LoadLibraryA("vulkan-1.dll");
    if (!loader.handle) return false;
    void* sym_version = reinterpret_cast<void*>(GetProcAddress(
        static_cast<HMODULE>(loader.handle), "vkEnumerateInstanceVersion"));
    void* sym_extensions = reinterpret_cast<void*>(GetProcAddress(
        static_cast<HMODULE>(loader.handle), "vkEnumerateInstanceExtensionProperties"));
    loader.enumerate_instance_version =
        reinterpret_cast<EnumerateInstanceVersionFn>(sym_version);
    loader.enumerate_instance_extensions =
        reinterpret_cast<EnumerateInstanceExtensionPropertiesFn>(sym_extensions);
    return loader.enumerate_instance_version != nullptr;
#else
    return false;
#endif
}

// The instance extensions this backend knows how to talk about. The list is reported verbatim; the
// frontend never invents an extension name.
const char* kReportedInstanceExtensions[] = {
    "VK_KHR_surface",
    "VK_EXT_debug_utils",
    "VK_KHR_get_physical_device_properties2",
    "VK_KHR_portability_enumeration",
};

class VulkanBackend final : public IBackend {
public:
    const char* name() const override { return "vulkan"; }

    Capabilities capabilities() const override {
        Capabilities caps;
        caps.backend_name = "vulkan";

        VulkanLoader loader;
        if (!load_vulkan(loader)) {
            // The honest answer: no Vulkan. The frontend sees available = false and every operation
            // returns NotAvailable. Nothing is faked.
            return caps;
        }

        caps.available = true;
        caps.vulkan = true;

        uint32_t version = 0;
        if (loader.enumerate_instance_version && loader.enumerate_instance_version(&version) == 0) {
            caps.vulkan_api_version = version;
        }

        // Device-level features are not queried here: that needs an instance and a physical device,
        // which is a later phase. Reporting them as false is the honest default.
        caps.shader_translation = false;
        caps.argument_buffers = false;
        caps.descriptor_heap = false;
        return caps;
    }

    Result<std::shared_ptr<IBackendDevice>> create_device(const DeviceDescriptor&) override {
        // Phase 1: detection only. Creating a device needs a physical device, a queue family and a
        // real driver; none of that is assumed here.
        return Result<std::shared_ptr<IBackendDevice>>(Status::Unsupported);
    }

    std::vector<const char*> supported_extensions() const override {
        std::vector<const char*> names;
        VulkanLoader loader;
        if (!load_vulkan(loader) || !loader.enumerate_instance_extensions) return names;

        uint32_t count = 0;
        if (loader.enumerate_instance_extensions(nullptr, &count, nullptr) != 0 || count == 0) {
            return names;
        }
        struct ExtensionProperties {
            char name[256];
            uint32_t spec_version;
        };
        std::vector<ExtensionProperties> properties(count);
        if (loader.enumerate_instance_extensions(nullptr, &count, properties.data()) != 0) {
            return names;
        }
        for (const char* reported : kReportedInstanceExtensions) {
            for (const auto& property : properties) {
                if (std::string(property.name) == reported) {
                    names.push_back(reported);
                    break;
                }
            }
        }
        return names;
    }
};

}   // namespace

BackendPtr create_vulkan_backend() {
    return std::make_shared<VulkanBackend>();
}

}   // namespace hakimetal
