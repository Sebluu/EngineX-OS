// Private QEMU preview adapter: give Qt's minimal EGL platform a fixed pbuffer.
// No display device, GPU or firmware file is exposed to the host.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
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

EGLBoolean eglMakeCurrent(EGLDisplay display, EGLSurface draw, EGLSurface read, EGLContext context) {
    typedef EGLBoolean (*current_fn)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);
    current_fn current = (current_fn)dlsym(RTLD_NEXT, "eglMakeCurrent");
    EGLBoolean result = current ? current(display, draw, read, context) : EGL_FALSE;
    static atomic_int logged;
    if (result && context != EGL_NO_CONTEXT && enabled() && !atomic_exchange(&logged, 1)) {
        typedef void (*function_ptr)(void);
        typedef function_ptr (*resolve_fn)(const char *);
        typedef const unsigned char *(*string_fn)(unsigned int);
        resolve_fn resolve = (resolve_fn)dlsym(RTLD_NEXT, "eglGetProcAddress");
        string_fn string = resolve ? (string_fn)resolve("glGetString") : NULL;
        const unsigned char *renderer = string ? string(0x1F01 /* GL_RENDERER */) : NULL;
        if (renderer) fprintf(stderr, "PREVIEW_GL_RENDERER %s\n", (const char *)renderer);
    }
    return result;
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

static double milliseconds(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return 0;
    return now.tv_sec * 1000.0 + now.tv_nsec / 1000000.0;
}

static void capture_frame(EGLDisplay display, EGLSurface surface) {
    // A swap already contains the rendered scene. Re-rendering with
    // QQuickWindow::grabWindow and PNG compression in ARM blocked GUI input.
    static atomic_flag busy = ATOMIC_FLAG_INIT;
    static double last;
    static unsigned long long frame;
    static unsigned char *pixels;
    static size_t capacity;
    const double started = milliseconds();
    if (atomic_flag_test_and_set(&busy)) return;
    if (started - last < 100) goto done;
    EGLint width = 0, height = 0;
    typedef EGLBoolean (*query_fn)(EGLDisplay, EGLSurface, EGLint, EGLint *);
    query_fn query = (query_fn)dlsym(RTLD_NEXT, "eglQuerySurface");
    if (!query || !query(display, surface, EGL_WIDTH, &width) ||
        !query(display, surface, EGL_HEIGHT, &height) || width < 640 || height < 400 ||
        width > 1280 || height > 800) goto done;
    const char *session = getenv("ENGINEX_PREVIEW_SESSION");
    if (!session || strlen(session) != 36 || strspn(session, "0123456789abcdef-") != 36) goto done;
    typedef void (*function_ptr)(void);
    typedef function_ptr (*resolve_fn)(const char *);
    resolve_fn resolve = (resolve_fn)dlsym(RTLD_NEXT, "eglGetProcAddress");
    if (!resolve) goto done;
    typedef void (*get_fn)(unsigned int, int *);
    typedef void (*bind_fn)(unsigned int, unsigned int);
    typedef void (*store_fn)(unsigned int, int);
    typedef void (*read_fn)(int, int, int, int, unsigned int, unsigned int, void *);
    typedef const unsigned char *(*string_fn)(unsigned int);
    get_fn get = (get_fn)resolve("glGetIntegerv");
    bind_fn bind = (bind_fn)resolve("glBindFramebuffer");
    bind_fn bind_buffer = (bind_fn)resolve("glBindBuffer");
    store_fn store = (store_fn)resolve("glPixelStorei");
    read_fn read = (read_fn)resolve("glReadPixels");
    string_fn string = (string_fn)resolve("glGetString");
    if (!get || !bind || !bind_buffer || !store || !read || !string) goto done;
    const char *version = (const char *)string(0x1F02 /* GL_VERSION */);
    if (!version) goto done;
    const char *es = strstr(version, "OpenGL ES ");
    const int advanced = atoi(es ? es + 10 : version) >= 3;
    const size_t size = (size_t)width * (size_t)height * 4;
    if (capacity != size) {
        unsigned char *replacement = calloc(1, size);
        if (!replacement) goto done;
        free(pixels); pixels = replacement; capacity = size;
    }
    int draw = 0, read_buffer = 0, pack = 0, row_length = 0, skip_rows = 0, skip_pixels = 0;
    get(0x8CA6 /* GL_DRAW_FRAMEBUFFER_BINDING */, &draw);
    if (advanced) {
        get(0x8CAA /* GL_READ_FRAMEBUFFER_BINDING */, &read_buffer);
        get(0x88ED /* GL_PIXEL_PACK_BUFFER_BINDING */, &pack);
        get(0x0D02 /* GL_PACK_ROW_LENGTH */, &row_length);
        get(0x0D03 /* GL_PACK_SKIP_ROWS */, &skip_rows);
        get(0x0D04 /* GL_PACK_SKIP_PIXELS */, &skip_pixels);
        bind(0x8CA8 /* GL_READ_FRAMEBUFFER */, 0);
        bind_buffer(0x88EB /* GL_PIXEL_PACK_BUFFER */, 0);
        store(0x0D02, 0); store(0x0D03, 0); store(0x0D04, 0);
    } else {
        bind(0x8D40 /* GL_FRAMEBUFFER */, 0);
    }
    read(0, 0, width, height, 0x1908 /* GL_RGBA */, 0x1401 /* GL_UNSIGNED_BYTE */, pixels);
    if (advanced) {
        store(0x0D02, row_length); store(0x0D03, skip_rows); store(0x0D04, skip_pixels);
        bind_buffer(0x88EB, (unsigned int)pack);
        bind(0x8CA8, (unsigned int)read_buffer);
    } else {
        bind(0x8D40, (unsigned int)draw);
    }
    const double elapsed = milliseconds() - started;
    int fd = open("/tmp/preview/frame.new.raw", O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    FILE *output = fd < 0 ? NULL : fdopen(fd, "wb");
    if (!output) { if (fd >= 0) close(fd); goto done; }
    ++frame;
    fprintf(output, "{\"width\":%d,\"height\":%d,\"stride\":%d,\"format\":\"RGBA\",\"frame\":%llu,\"stream\":\"%s\",\"renderer\":\"opengl\",\"capturedAtMs\":%.2f,\"readbackMs\":%.2f}\n",
            width, height, width * 4, frame, session, started, elapsed);
    int ok = fwrite(pixels, 1, size, output) == size;
    if (fclose(output)) ok = 0;
    if (ok) rename("/tmp/preview/frame.new.raw", "/tmp/preview/frame.raw");
    if (ok && frame == 1) fprintf(stderr, "PREVIEW_SWAP_CAPTURE %dx%d readback=%.2fms %s\n", width, height, elapsed, version);
    last = started;
done:
    atomic_flag_clear(&busy);
}

EGLBoolean eglSwapBuffers(EGLDisplay display, EGLSurface surface) {
    typedef EGLBoolean (*swap_fn)(EGLDisplay, EGLSurface);
    swap_fn swap = (swap_fn)dlsym(RTLD_NEXT, "eglSwapBuffers");
    if (enabled()) capture_frame(display, surface);
    return swap ? swap(display, surface) : EGL_FALSE;
}
