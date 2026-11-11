#ifndef HAKIMETAL_HAKIMETAL_H
#define HAKIMETAL_HAKIMETAL_H

// HakiMetal -- an experimental, backend-independent graphics API for HakiOS.
//
// HakiMetal is not Apple Metal and is not compatible with it. It follows the object model of Apple's
// documented Metal concepts and puts them behind a backend interface. No Metal source compiles against
// it unchanged, no Metal binary runs on it, and nothing here claims otherwise.
//
// Vulkan is one possible backend and is not assumed to exist. The Vulkan backend reports absence
// rather than pretending. Nothing in this project writes GPU registers.

#include "hakimetal/backend.h"
#include "hakimetal/buffer.h"
#include "hakimetal/command_buffer.h"
#include "hakimetal/command_queue.h"
#include "hakimetal/device.h"
#include "hakimetal/registry.h"
#include "hakimetal/render_pipeline.h"
#include "hakimetal/synchronization.h"
#include "hakimetal/texture.h"
#include "hakimetal/types.h"

#endif   // HAKIMETAL_HAKIMETAL_H
