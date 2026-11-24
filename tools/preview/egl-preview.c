// Private QEMU preview adapter: give Qt's minimal EGL platform a fixed pbuffer.
// No display device, GPU or firmware file is exposed to the host.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <EGL/egl.h>

static int enabled(void) {
    const char *value = getenv("ENGINEX_DESKTOP_PREVIEW");
    return value && !strcmp(value, "1") && !access("/run/enginex-desktop-preview", F_OK);
}

__attribute__((constructor)) static void isolate_preloads(void) {
    // Mesa belongs to this Engine process. Non-Qt child programs keep using
    // the vendor runtime; the already-loaded libraries stay in Engine.
    if (enabled()) unsetenv("LD_PRELOAD");
}

EGLDisplay eglGetDisplay(EGLNativeDisplayType native) {
    if (enabled()) {
        void *vendor = dlopen("/opt/enginex-preview-mesa/usr/lib/arm-linux-gnueabihf/libEGL_mesa.so.0", RTLD_NOW | RTLD_LOCAL);
        if (!vendor) fprintf(stderr, "PREVIEW_MESA_LOAD %s\n", dlerror());
        // GLVND 1.7 does not recognize EGL_PLATFORM=surfaceless in its legacy
        // eglGetDisplay dispatcher. Request Mesa's platform explicitly.
        typedef EGLDisplay (*platform_fn)(EGLenum, void *, const EGLAttrib *);
        platform_fn get = (platform_fn)dlsym(RTLD_NEXT, "eglGetPlatformDisplay");
        EGLDisplay display = get ? get(0x31DD /* EGL_PLATFORM_SURFACELESS_MESA */, NULL, NULL) : EGL_NO_DISPLAY;
        fprintf(stderr, "PREVIEW_EGL_DISPLAY surfaceless=%d\n", display != EGL_NO_DISPLAY);
        return display;
    }
    typedef EGLDisplay (*display_fn)(EGLNativeDisplayType);
    display_fn get = (display_fn)dlsym(RTLD_NEXT, "eglGetDisplay");
    return get ? get(native) : EGL_NO_DISPLAY;
}

EGLBoolean eglChooseConfig(EGLDisplay display, const EGLint *attributes,
                          EGLConfig *configs, EGLint size, EGLint *count) {
    typedef EGLBoolean (*choose_fn)(EGLDisplay, const EGLint *, EGLConfig *, EGLint, EGLint *);
    choose_fn choose = (choose_fn)dlsym(RTLD_NEXT, "eglChooseConfig");
    if (!choose) return EGL_FALSE;
    if (!enabled() || !attributes) return choose(display, attributes, configs, size, count);
    EGLint copy[129];
    int i = 0;
    for (; i < 126 && attributes[i] != EGL_NONE; i += 2) {
        copy[i] = attributes[i];
        copy[i + 1] = attributes[i] == EGL_SURFACE_TYPE ? EGL_PBUFFER_BIT : attributes[i + 1];
    }
    if (attributes[i] != EGL_NONE) return EGL_FALSE;
    copy[i] = EGL_NONE;
    return choose(display, copy, configs, size, count);
}

EGLSurface eglCreateWindowSurface(EGLDisplay display, EGLConfig config,
                                  EGLNativeWindowType window, const EGLint *attributes) {
    if (enabled()) {
        typedef EGLSurface (*pbuffer_fn)(EGLDisplay, EGLConfig, const EGLint *);
        pbuffer_fn create = (pbuffer_fn)dlsym(RTLD_NEXT, "eglCreatePbufferSurface");
        const EGLint dimensions[] = {EGL_WIDTH, 1280, EGL_HEIGHT, 800, EGL_NONE};
        return create ? create(display, config, dimensions) : EGL_NO_SURFACE;
    }
    typedef EGLSurface (*window_fn)(EGLDisplay, EGLConfig, EGLNativeWindowType, const EGLint *);
    window_fn create = (window_fn)dlsym(RTLD_NEXT, "eglCreateWindowSurface");
    return create ? create(display, config, window, attributes) : EGL_NO_SURFACE;
}
