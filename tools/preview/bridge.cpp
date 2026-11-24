// Desktop preview only. This library is never included in an EngineX image or Mod.
#include <QCoreApplication>
#include <QGuiApplication>
#include <QGenericPlugin>
#include <QElapsedTimer>
#include <QImage>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPointer>
#include <QQuickWindow>
#include <QTimer>
#include <QtTest/qtestspontaneevent.h>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

// QtGui's test event entry points, declared in QtTest's public mouse/keyboard
// headers. Signatures verified against the pinned firmware's Qt 6.7.2 source.
// Weak references keep capture available on a build without test support.
QT_BEGIN_NAMESPACE
extern void qt_handleMouseEvent(QWindow *, const QPointF &, const QPointF &,
    Qt::MouseButtons, Qt::MouseButton, QEvent::Type, Qt::KeyboardModifiers, int) __attribute__((weak));
extern void qt_handleKeyEvent(QWindow *, QEvent::Type, int, Qt::KeyboardModifiers,
    const QString &, bool, ushort) __attribute__((weak));
QT_END_NAMESPACE

namespace {
constexpr const char *directory = "/tmp/preview";
int input = -1;
quint64 frame = 0;
QElapsedTimer clock;
QPointer<QQuickWindow> selected;

QQuickWindow *window() {
    if (selected && selected->isVisible()) return selected;
    QQuickWindow *largest = nullptr;
    for (QWindow *candidate : QGuiApplication::allWindows()) {
        auto *quick = qobject_cast<QQuickWindow *>(candidate);
        if (quick && quick->isVisible() && quick->width() > 100 && quick->height() > 100 &&
            (!largest || quick->width() * quick->height() > largest->width() * largest->height())) largest = quick;
    }
    selected = largest;
    if (largest) {
        largest->resize(1280, 800);
        largest->requestActivate();
    }
    return largest;
}

void dispatch() {
    auto *target = window();
    char packet[256];
    // Bounded work: excess mouse moves wait until the next GUI tick.
    for (int count = 0; count < 32; ++count) {
        const auto length = recv(input, packet, sizeof(packet) - 1, MSG_DONTWAIT);
        if (length < 0) break;
        packet[length] = 0;
        if (!target) continue;
        int action, button, buttons, modifiers, key;
        unsigned int character;
        double x, y;
        if (sscanf(packet, "M %d %lf %lf %d %d %d", &action, &x, &y, &button, &buttons, &modifiers) == 6) {
            if (action < 1 || action > 3 || !std::isfinite(x) || !std::isfinite(y) ||
                x < 0 || y < 0 || x >= target->width() || y >= target->height() ||
                button < 0 || button > 4 || buttons < 0 || buttons > 7 || (modifiers & ~0x1e000000)) continue;
            const auto type = action == 1 ? QEvent::MouseButtonPress : action == 3 ? QEvent::MouseButtonRelease : QEvent::MouseMove;
            const QPointF local(x, y);
            const QPointF global = target->mapToGlobal(local.toPoint());
            if (qt_handleMouseEvent) {
                qt_handleMouseEvent(target, local, global,
                    Qt::MouseButtons(static_cast<Qt::MouseButton>(buttons)),
                    static_cast<Qt::MouseButton>(button), type,
                    Qt::KeyboardModifiers(static_cast<Qt::KeyboardModifier>(modifiers)),
                    static_cast<int>(clock.elapsed()) + 1);
                continue;
            }
            QMouseEvent event(type, local, local, global, static_cast<Qt::MouseButton>(button),
                              Qt::MouseButtons(static_cast<Qt::MouseButton>(buttons)),
                              Qt::KeyboardModifiers(static_cast<Qt::KeyboardModifier>(modifiers)));
            event.setTimestamp(static_cast<quint64>(clock.elapsed()) + 1);
            // Fallback for a Qt build without the window-system test entry point.
            QSpontaneKeyEvent::setSpontaneous(&event);
            QCoreApplication::instance()->notify(target, &event);
        } else if (sscanf(packet, "K %d %d %d %u", &action, &key, &modifiers, &character) == 4) {
            if ((action != 1 && action != 3) || key < 0 || key > 0x1ffffff || character > 0x10ffff ||
                (character >= 0xd800 && character <= 0xdfff) || (modifiers & ~0x1e000000)) continue;
            const char32_t point = character;
            const QString text = character ? QString::fromUcs4(&point, 1) : QString();
            if (qt_handleKeyEvent) {
                qt_handleKeyEvent(target, action == 1 ? QEvent::KeyPress : QEvent::KeyRelease,
                    key, Qt::KeyboardModifiers(static_cast<Qt::KeyboardModifier>(modifiers)), text, false, 1);
                continue;
            }
            QKeyEvent event(action == 1 ? QEvent::KeyPress : QEvent::KeyRelease, key,
                            Qt::KeyboardModifiers(static_cast<Qt::KeyboardModifier>(modifiers)), text);
            event.setTimestamp(static_cast<quint64>(clock.elapsed()) + 1);
            QSpontaneKeyEvent::setSpontaneous(&event);
            QCoreApplication::instance()->notify(target, &event);
        }
    }
}

void capture() {
    auto *target = window();
    if (!target) return;
    const QImage image = target->grabWindow();
    if (image.isNull()) return;
    if (!image.save(QString::fromLatin1(directory) + "/frame.new.png", "PNG", 35)) return;
    if (rename("/tmp/preview/frame.new.png", "/tmp/preview/frame.png")) return;
    FILE *meta = fopen("/tmp/preview/frame.new.json", "w");
    if (!meta) return;
    fprintf(meta, "{\"width\":%d,\"height\":%d,\"frame\":%llu,\"renderer\":\"software\"}\n",
            image.width(), image.height(), static_cast<unsigned long long>(++frame));
    fclose(meta);
    rename("/tmp/preview/frame.new.json", "/tmp/preview/frame.json");
}

void start() {
    clock.start();
    mkdir(directory, 0700);
    input = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (input < 0) { fprintf(stderr, "PREVIEW_SOCKET_ERROR %s\n", strerror(errno)); return; }
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    strncpy(address.sun_path, "/tmp/preview/control.sock", sizeof(address.sun_path) - 1);
    unlink(address.sun_path);
    if (bind(input, reinterpret_cast<sockaddr *>(&address), sizeof(address))) {
        fprintf(stderr, "PREVIEW_BIND_ERROR %s\n", strerror(errno));
        close(input); input = -1; return;
    }
    chmod(address.sun_path, 0600);
    auto *events = new QTimer(QCoreApplication::instance());
    QObject::connect(events, &QTimer::timeout, QCoreApplication::instance(), dispatch);
    events->start(20);
    auto *pictures = new QTimer(QCoreApplication::instance());
    QObject::connect(pictures, &QTimer::timeout, QCoreApplication::instance(), capture);
    pictures->start(750);
    fprintf(stderr, "PREVIEW_BRIDGE_READY Qt=%s\n", qVersion());
    fprintf(stderr, "PREVIEW_GUI_INPUT mouse=%d keyboard=%d\n", qt_handleMouseEvent != nullptr, qt_handleKeyEvent != nullptr);
}

}

// Loaded by Qt after its libraries are present. It must not be in LD_PRELOAD:
// Engine's non-Qt subprocesses (including lscpu) inherit that variable.
class DesktopPreviewPlugin final : public QGenericPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QGenericPluginFactoryInterface_iid FILE "plugin.json")
public:
    QObject *create(const QString &name, const QString &) override {
        const char *enabled = getenv("ENGINEX_DESKTOP_PREVIEW");
        fprintf(stderr, "PREVIEW_PLUGIN_CREATE Qt=%s enabled=%d marker=%d\n", qVersion(), enabled && !strcmp(enabled,"1"), access("/run/enginex-desktop-preview", F_OK)==0);
        if (name != QStringLiteral("enginexpreview") || !enabled || strcmp(enabled, "1") ||
            access("/run/enginex-desktop-preview", F_OK) || strncmp(qVersion(), "6.", 2)) return nullptr;
        QTimer::singleShot(0, QCoreApplication::instance(), start);
        return new QObject();
    }
};

#include "bridge.moc"
